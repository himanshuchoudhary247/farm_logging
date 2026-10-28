"""Conversational shop order -- lets a farmer order a product from their own
FlokIQ store by chatting with Chocolate, then pay in the app with the same
Razorpay checkout the Shop's cart uses.

One product per order: product -> quantity -> delivery address -> confirm ->
order. Voice and chat replies that mix several products and quantities are
easy to misread, and the farmer should always see exactly what they are
ordering before saying yes. (main_backend's order route already accepts
several items, so a "add another product?" step can be added here later
without any backend change.)

Everything about the order lives in main_backend (services/flokiq_sync's
search_products / quote_order / create_order): which products this farmer
can order, the price (member price for FlokIQ members), the stock and the
order itself. This agent never computes a price -- it shows main_backend's
quote, and the amount the farmer pays is the one main_backend saved. There
is no local copy of an order and no "sync later": if main_backend cannot be
reached, the farmer is told so.

Same machinery as the other multi-turn agents (DraftSupervisor: per-session
draft file and lock) and the same extraction style as animal_registration:
one dedicated tool call per turn, the LLM is the primary reader of the
farmer's words, and services/common/reply_words.py is only a fallback.

Kill switch: CHAT_ORDERS_ENABLED must be "true" (default off, like
FLOKIQ_SYNC_ENABLED), otherwise the farmer is told ordering through chat
is not available and nothing is called.

Product photos: main_backend sends each product's `image` as it stores it
(products.image, the uploaded file's name, or empty when the product has no
photo). The app turns it into a link the same way the Shop does
(VITE_PUBLIC_API_FILE_PATHS + name). Only a plain file name is passed on --
see _image_file -- and CHAT_ORDER_IMAGES_ENABLED=false stops sending photos
without touching the rest of the order flow.
"""
from __future__ import annotations

import logging
import os
import re
from base64 import b64encode
from typing import Any, Callable, Optional

from services.common import reply_words
from services.common.draft_supervisor import (
    DraftSupervisor,
    SUPPORTED_LANGUAGES,
    _UNSET,
    _lang,
)
from services.flokiq_sync import client as flokiq_sync
from services.llm_service.bedrock_adapter import BedrockTextAdapter, TaskTier
from services.voice_agent.tts import synthesize_speech

_log = logging.getLogger("order_supervisor")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

_TRUTHY = {"1", "true", "yes", "on"}

# Same per-item limit main_backend enforces (and the app's cart uses).
MAX_QUANTITY = 10
# How many matching products are offered at once.
MAX_CHOICES = 5
# Quantity pills offered, trimmed to what can actually be ordered.
_QUANTITY_PILLS = (1, 2, 3, 5, 10)
# A typed address shorter than this is not treated as an address.
_MIN_ADDRESS_LENGTH = 5
# Longest product photo file name passed on (main_backend's products.image
# column is varchar(255)).
_MAX_IMAGE_NAME_LENGTH = 255
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
# Words that make a number a pack size ("500 ml", "1 L"), not a quantity.
_PACK_SIZE_UNITS = {"ml", "l", "ltr", "ltrs", "litre", "litres", "liter", "liters",
                    "kg", "kgs", "g", "gm", "gms", "gram", "grams", "mg"}
# Messages the order agent lets go of when it finds nothing for the order in
# them: the other agents' areas, as named by the router's intent classifier.
# Not "query" -- the classifier's catch-all, which also covers "ok" or a
# price question that belong to the order.
RELEASE_TOPICS = ("weather", "appointment", "add_animal")

# States. CANCELLED and ORDERED end the conversation (the router stops
# sending this session's messages here); anything else is still in progress.
SEARCHING = "SEARCHING"
CHOOSING = "CHOOSING"
QUANTITY = "QUANTITY"
ADDRESS = "ADDRESS"
CONFIRMING = "CONFIRMING"
CORRECTING = "CORRECTING"
ORDERED = "ORDERED"
CANCELLED = "CANCELLED"


def chat_orders_enabled() -> bool:
    return os.getenv("CHAT_ORDERS_ENABLED", "").strip().lower() in _TRUTHY


def chat_order_images_enabled() -> bool:
    """Product photos in the chat order flow. On unless
    CHAT_ORDER_IMAGES_ENABLED is set to something that is not truthy (e.g.
    "false"); unset or empty keeps them on."""
    value = os.getenv("CHAT_ORDER_IMAGES_ENABLED", "").strip().lower()
    return not value or value in _TRUTHY


def _image_file(value: Any) -> Optional[str]:
    """The product photo's file name as main_backend stores it
    (products.image), trimmed -- or None, and the app shows no photo. None
    for: no value, an empty one (a product without a photo), anything that is
    not a string, a name longer than the column allows, and anything that is
    not a plain file name (a full link, a path with folders, "." or "..",
    control characters), since the app puts it straight after its own
    uploads address."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > _MAX_IMAGE_NAME_LENGTH or name in {".", ".."}:
        return None
    if "/" in name or "\\" in name or _CONTROL_CHARACTERS.search(name):
        return None
    return name


def _with_checked_image(product: dict[str, Any]) -> dict[str, Any]:
    """A copy of main_backend's product with `image` replaced by the checked
    file name (or None; always None when photos are switched off)."""
    image = _image_file(product.get("image")) if chat_order_images_enabled() else None
    return {**product, "image": image}


def _number_in_text(text: str) -> Optional[int]:
    """A quantity typed as digits next to the product ("2 calcium gel",
    "calcium gel chahiye 2"), for when the LLM returned none. Only exactly
    one standalone number from 1 to MAX_QUANTITY that is not a pack size
    ("500 ml", "1 L"); anything else (no number, several, a PIN code) ->
    None, and the agent asks how many. Digits of any script count."""
    words = re.findall(r"[^\W_]+", text or "")
    numbers = [i for i, word in enumerate(words) if word.isdecimal()]
    if len(numbers) != 1:
        return None
    index = numbers[0]
    if index + 1 < len(words) and words[index + 1].lower() in _PACK_SIZE_UNITS:
        return None
    number = int(words[index])
    return number if 1 <= number <= MAX_QUANTITY else None


def _money(value: Any) -> str:
    """Rupees for display: whole amounts without decimals (240), others with
    two (240.50)."""
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError):
        return str(value)
    return str(int(amount)) if amount == int(amount) else f"{amount:.2f}"


def _price_varies(unit_price: Any, quantity: Any, total: Any) -> bool:
    """True when main_backend's total is not quantity x the price shown for
    one: the store sells the oldest stock first, and stock bought at
    different times can carry different prices, so the units ordered may
    not all cost the same. False whenever a value is missing or not a
    number (nothing is said then)."""
    try:
        unit, count, amount = float(unit_price), int(quantity), float(total)
    except (TypeError, ValueError):
        return False
    if unit <= 0 or count <= 0 or amount <= 0:
        return False
    return abs(round(unit * count, 2) - round(amount, 2)) >= 0.01


def _choice_label(product: dict[str, Any]) -> str:
    """The pill text for a product. Includes the pack so two packs of the
    same product stay distinguishable; a tapped pill comes back as this exact
    text and is matched against it."""
    name = str(product.get("name") or "").strip()
    pack = str(product.get("packType") or "").strip()
    return f"{name} ({pack})" if pack and pack.lower() not in name.lower() else name


_ORDER_TOOL_SPEC = {
    "name": "record_order_turn",
    "description": (
        "Record what the farmer said in this turn of ordering a product from their shop. "
        "Populate ONLY what the farmer actually said in THIS message -- never invent a value "
        "and never repeat something from an earlier turn (the caller remembers it). Call this "
        "tool exactly once every turn, with every property omitted if the message states "
        "nothing new. Never answer with plain text instead."
    ),
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "product_query": {
                    "type": "string",
                    "description": (
                        "Short ENGLISH search words for the product the farmer wants, when they "
                        "name or describe a product in this message. Translate from any language "
                        "and keep only the product's own words (name, brand, ingredient or type), "
                        "e.g. 'calcium gel', 'dewormer', 'mineral mixture'. No quantity, no words "
                        "like 'medicine', 'want', 'order'. Omit when no product is named."
                    ),
                },
                "chosen_option": {
                    "type": "integer",
                    "description": (
                        "When the farmer picks one of the numbered OPTIONS given in the context "
                        "(by name, by its number, or by a clear description), its number. Omit "
                        "otherwise, and never pick one the farmer did not clearly mean."
                    ),
                },
                "quantity": {
                    "type": "integer",
                    "description": (
                        "How many units the farmer wants, only when clearly stated in this "
                        "message, in any language ('2', 'two', 'do', 'don') -- also when the "
                        "product is named in the same message, before or after the number. A bare "
                        "number answers the quantity when the farmer was just asked how many. Not "
                        "a pack size ('500 ml', '1 L'). Never guess."
                    ),
                },
                "delivery_address": {
                    "type": "string",
                    "description": (
                        "A delivery address the farmer gives in this message, exactly as said. "
                        "Only when they actually state an address (or were just asked for one and "
                        "reply with it). Omit otherwise."
                    ),
                },
                "off_topic": {
                    "type": "boolean",
                    "description": (
                        "true ONLY when the message is about something else entirely, not this "
                        "order -- e.g. the weather, a sick animal, booking a vet, or a question "
                        "about their animals or records. false for anything to do with the order "
                        "(a product, a number, an address, yes/no, a price question, a question "
                        "about delivery or payment)."
                    ),
                },
                "confirmation_signal": {
                    "type": "string",
                    "enum": ["yes", "no", "cancel", "none"],
                    "description": (
                        "Classify the message by meaning: 'yes' agrees to place the order shown, "
                        "'no' rejects it or wants to change something, 'cancel' abandons ordering, "
                        "'none' for anything else (naming a product, a quantity, a question). "
                        "By meaning, not keywords: 'no problem, go ahead' is 'yes'; 'leave it, I "
                        "don't want anything' is 'cancel'."
                    ),
                },
            },
        }
    },
}

_ORDER_SYSTEM = """You help a farmer order ONE product from their own FlokIQ shop, step by step.

You are told what was just asked and what is already known. Extract only what the farmer's message itself says; never invent a product, number or address.

Examples (what goes into record_order_turn):
1) Nothing known yet | Farmer: "I need calcium gel for my goats" -> {product_query: 'calcium gel'}
2) Nothing known yet | Farmer: "बकरी के कीड़े की दवा चाहिए, 2 पैकेट" -> {product_query: 'dewormer', quantity: 2}
3) OPTIONS: 1. Calcium Gel (1 L), 2. Calcium Plus (500 ml) | Farmer: "the second one" -> {chosen_option: 2}
4) OPTIONS: 1. Calcium Gel (1 L), 2. Calcium Plus (500 ml) | Farmer: "Calcium Plus" -> {chosen_option: 2}
5) Just asked how many | Farmer: "3" -> {quantity: 3}
6) Just asked how many | Farmer: "दोन" -> {quantity: 2}
7) Just asked for the delivery address | Farmer: "Near the temple, Wakad, Pune 411057" -> {delivery_address: 'Near the temple, Wakad, Pune 411057'}
8) Asked to confirm the order | Farmer: "haan kar do" -> {confirmation_signal: 'yes'}
9) Asked to confirm the order | Farmer: "no, make it 4" -> {confirmation_signal: 'no', quantity: 4}
10) Any step | Farmer: "rehne do, kuch nahi chahiye" -> {confirmation_signal: 'cancel'}
11) Just asked how many | Farmer: "will it rain tomorrow?" -> {off_topic: true}
12) Just asked how many | Farmer: "what does it cost?" -> {} -- about the order, not off topic
13) Nothing known yet | Farmer: "5 mineral mixture packet bhej do" -> {product_query: 'mineral mixture', quantity: 5}
14) Nothing known yet | Farmer: "liver tonic chahiye 3" -> {product_query: 'liver tonic', quantity: 3}
15) Just asked how many | Farmer: "haan ji" -> {confirmation_signal: 'yes'} -- a yes is not a number, no quantity"""


_YES_NO = {
    "en": ("Yes", "No"),
    "hi": ("हाँ", "नहीं"),
    "mr": ("हो", "नाही"),
    "ta": ("ஆம்", "இல்லை"),
    "te": ("అవును", "కాదు"),
    "kn": ("ಹೌದು", "ಇಲ್ಲ"),
    "ml": ("അതെ", "ഇല്ല"),
}

_OTHER_LABEL = {
    "en": "Other",
    "hi": "अन्य",
    "mr": "इतर",
    "ta": "மற்றவை",
    "te": "ఇతర",
    "kn": "ಇತರ",
    "ml": "മറ്റുള്ളവ",
}

_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Which product would you like to order? Tell me its name, for example a medicine, feed or supplement.",
        "unavailable": "Ordering through chat is not available right now. You can order from the Shop in the app.",
        "no_store": "Your account is not linked to a store yet, so I cannot place an order here. Please contact your FlokIQ store.",
        "shop_unreachable": "I could not reach the shop right now. Please try again in a moment.",
        "not_found": "I could not find '{query}' in your store. Please tell me another name for the product.",
        "choose": "I found these in your store: {options}. Which one would you like?",
        "ask_quantity": "{product} costs ₹{price} each. How many would you like? You can order up to {max}.",
        "too_many": "Only {available} of {product} can be ordered right now. How many would you like?",
        "out_of_stock": "{product} is out of stock right now. Would you like something else?",
        "ask_address": "Where should it be delivered? Please tell me the full address.",
        "confirm": "{quantity} x {product} = ₹{total}. Delivery address: {address}. Shall I place the order?",
        "prescription": "This product needs a vet's prescription.",
        "batch_price": "Some of these come from stock with a different price, so the total is not exactly {quantity} x ₹{price}.",
        "what_to_change": "What would you like to change: the product, the quantity or the address?",
        "stock_changed": "The stock or price of {product} changed just now. How many would you like?",
        "placed": "Your order {code} is placed: {quantity} x {product}, ₹{total}. Tap Pay to complete the payment.",
        "payment_retry": "Your order is saved, but the payment could not be started. Say yes to try again.",
        "order_failed": "I could not place the order right now. Say yes to try again, or cancel.",
        "cancelled": "Okay, I cancelled it. Nothing was ordered.",
    },
    "hi": {
        "welcome": "आप कौन सा सामान ऑर्डर करना चाहते हैं? उसका नाम बताइए, जैसे कोई दवा, चारा या सप्लीमेंट।",
        "unavailable": "अभी चैट से ऑर्डर उपलब्ध नहीं है। आप ऐप की शॉप से ऑर्डर कर सकते हैं।",
        "no_store": "आपका खाता अभी किसी दुकान से जुड़ा नहीं है, इसलिए मैं यहाँ ऑर्डर नहीं कर सकता। कृपया अपनी FlokIQ दुकान से संपर्क करें।",
        "shop_unreachable": "अभी दुकान से संपर्क नहीं हो पाया। कृपया थोड़ी देर बाद फिर कोशिश करें।",
        "not_found": "आपकी दुकान में '{query}' नहीं मिला। कृपया सामान का कोई दूसरा नाम बताइए।",
        "choose": "आपकी दुकान में ये मिले: {options}। आपको कौन सा चाहिए?",
        "ask_quantity": "एक {product} का दाम ₹{price} है। आपको कितने चाहिए? आप ज़्यादा से ज़्यादा {max} ऑर्डर कर सकते हैं।",
        "too_many": "अभी {product} के सिर्फ़ {available} ऑर्डर हो सकते हैं। आपको कितने चाहिए?",
        "out_of_stock": "{product} अभी स्टॉक में नहीं है। क्या आपको कुछ और चाहिए?",
        "ask_address": "सामान कहाँ पहुँचाना है? कृपया पूरा पता बताइए।",
        "confirm": "{quantity} x {product} = ₹{total}। डिलीवरी का पता: {address}। क्या मैं ऑर्डर कर दूँ?",
        "prescription": "इस सामान के लिए पशु डॉक्टर का पर्चा ज़रूरी है।",
        "batch_price": "इनमें से कुछ अलग दाम वाले स्टॉक से हैं, इसलिए कुल रकम ठीक {quantity} x ₹{price} नहीं है।",
        "what_to_change": "आप क्या बदलना चाहते हैं: सामान, मात्रा या पता?",
        "stock_changed": "{product} का स्टॉक या दाम अभी बदल गया है। आपको कितने चाहिए?",
        "placed": "आपका ऑर्डर {code} हो गया: {quantity} x {product}, ₹{total}। भुगतान पूरा करने के लिए Pay दबाइए।",
        "payment_retry": "आपका ऑर्डर सेव हो गया है, लेकिन भुगतान शुरू नहीं हो पाया। फिर से कोशिश के लिए हाँ कहिए।",
        "order_failed": "अभी ऑर्डर नहीं हो पाया। फिर से कोशिश के लिए हाँ कहिए, या रद्द कीजिए।",
        "cancelled": "ठीक है, मैंने रद्द कर दिया। कुछ भी ऑर्डर नहीं हुआ।",
    },
    "mr": {
        "welcome": "तुम्हाला कोणती वस्तू ऑर्डर करायची आहे? तिचे नाव सांगा, जसे एखादे औषध, चारा किंवा सप्लिमेंट.",
        "unavailable": "सध्या चॅटमधून ऑर्डर उपलब्ध नाही. तुम्ही ॲपमधील शॉपमधून ऑर्डर करू शकता.",
        "no_store": "तुमचे खाते अजून कोणत्याही दुकानाशी जोडलेले नाही, त्यामुळे मी इथे ऑर्डर करू शकत नाही. कृपया तुमच्या FlokIQ दुकानाशी संपर्क करा.",
        "shop_unreachable": "सध्या दुकानाशी संपर्क होऊ शकला नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
        "not_found": "तुमच्या दुकानात '{query}' सापडले नाही. कृपया वस्तूचे दुसरे नाव सांगा.",
        "choose": "तुमच्या दुकानात हे सापडले: {options}. तुम्हाला कोणते हवे आहे?",
        "ask_quantity": "एका {product} ची किंमत ₹{price} आहे. तुम्हाला किती हवे आहेत? तुम्ही जास्तीत जास्त {max} ऑर्डर करू शकता.",
        "too_many": "सध्या {product} फक्त {available} ऑर्डर करता येतील. तुम्हाला किती हवे आहेत?",
        "out_of_stock": "{product} सध्या स्टॉकमध्ये नाही. तुम्हाला दुसरे काही हवे आहे का?",
        "ask_address": "वस्तू कुठे पोहोचवायची आहे? कृपया पूर्ण पत्ता सांगा.",
        "confirm": "{quantity} x {product} = ₹{total}. डिलिव्हरीचा पत्ता: {address}. मी ऑर्डर करू का?",
        "prescription": "या वस्तूसाठी पशुवैद्यकाची चिठ्ठी आवश्यक आहे.",
        "batch_price": "यातील काही वेगळ्या किमतीच्या स्टॉकमधून आहेत, त्यामुळे एकूण रक्कम नेमकी {quantity} x ₹{price} नाही.",
        "what_to_change": "तुम्हाला काय बदलायचे आहे: वस्तू, संख्या की पत्ता?",
        "stock_changed": "{product} चा स्टॉक किंवा किंमत आत्ताच बदलली आहे. तुम्हाला किती हवे आहेत?",
        "placed": "तुमची ऑर्डर {code} झाली: {quantity} x {product}, ₹{total}. पेमेंट पूर्ण करण्यासाठी Pay दाबा.",
        "payment_retry": "तुमची ऑर्डर सेव्ह झाली आहे, पण पेमेंट सुरू होऊ शकले नाही. पुन्हा प्रयत्नासाठी हो म्हणा.",
        "order_failed": "सध्या ऑर्डर होऊ शकली नाही. पुन्हा प्रयत्नासाठी हो म्हणा, किंवा रद्द करा.",
        "cancelled": "ठीक आहे, मी रद्द केले. काहीही ऑर्डर झाले नाही.",
    },
    "ta": {
        "welcome": "நீங்கள் எந்தப் பொருளை ஆர்டர் செய்ய விரும்புகிறீர்கள்? அதன் பெயரைச் சொல்லுங்கள், எ.கா. மருந்து, தீவனம் அல்லது சப்ளிமென்ட்.",
        "unavailable": "இப்போது சாட் மூலம் ஆர்டர் செய்ய முடியாது. ஆப்பில் உள்ள ஷாப்பில் ஆர்டர் செய்யலாம்.",
        "no_store": "உங்கள் கணக்கு இன்னும் எந்தக் கடையுடனும் இணைக்கப்படவில்லை, எனவே இங்கே ஆர்டர் செய்ய முடியாது. உங்கள் FlokIQ கடையைத் தொடர்பு கொள்ளுங்கள்.",
        "shop_unreachable": "இப்போது கடையை அணுக முடியவில்லை. சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும்.",
        "not_found": "உங்கள் கடையில் '{query}' கிடைக்கவில்லை. பொருளின் வேறு பெயரைச் சொல்லுங்கள்.",
        "choose": "உங்கள் கடையில் இவை கிடைத்தன: {options}. உங்களுக்கு எது வேண்டும்?",
        "ask_quantity": "ஒரு {product} விலை ₹{price}. உங்களுக்கு எத்தனை வேண்டும்? அதிகபட்சம் {max} ஆர்டர் செய்யலாம்.",
        "too_many": "இப்போது {product} {available} மட்டுமே ஆர்டர் செய்ய முடியும். உங்களுக்கு எத்தனை வேண்டும்?",
        "out_of_stock": "{product} இப்போது கையிருப்பில் இல்லை. வேறு ஏதாவது வேண்டுமா?",
        "ask_address": "எங்கே டெலிவரி செய்ய வேண்டும்? முழு முகவரியைச் சொல்லுங்கள்.",
        "confirm": "{quantity} x {product} = ₹{total}. டெலிவரி முகவரி: {address}. ஆர்டர் செய்யட்டுமா?",
        "prescription": "இந்தப் பொருளுக்கு கால்நடை மருத்துவரின் பரிந்துரைச் சீட்டு தேவை.",
        "batch_price": "இவற்றில் சில வேறு விலையுள்ள கையிருப்பிலிருந்து வருகின்றன, அதனால் மொத்தத் தொகை சரியாக {quantity} x ₹{price} அல்ல.",
        "what_to_change": "எதை மாற்ற விரும்புகிறீர்கள்: பொருள், எண்ணிக்கை அல்லது முகவரி?",
        "stock_changed": "{product} இன் கையிருப்பு அல்லது விலை இப்போது மாறிவிட்டது. உங்களுக்கு எத்தனை வேண்டும்?",
        "placed": "உங்கள் ஆர்டர் {code} செய்யப்பட்டது: {quantity} x {product}, ₹{total}. பணம் செலுத்த Pay அழுத்தவும்.",
        "payment_retry": "உங்கள் ஆர்டர் சேமிக்கப்பட்டது, ஆனால் பணம் செலுத்துதல் தொடங்கவில்லை. மீண்டும் முயற்சிக்க ஆம் என்று சொல்லுங்கள்.",
        "order_failed": "இப்போது ஆர்டர் செய்ய முடியவில்லை. மீண்டும் முயற்சிக்க ஆம் என்று சொல்லுங்கள், அல்லது ரத்து செய்யுங்கள்.",
        "cancelled": "சரி, ரத்து செய்துவிட்டேன். எதுவும் ஆர்டர் செய்யப்படவில்லை.",
    },
    "te": {
        "welcome": "మీరు ఏ వస్తువును ఆర్డర్ చేయాలనుకుంటున్నారు? దాని పేరు చెప్పండి, ఉదా. మందు, మేత లేదా సప్లిమెంట్.",
        "unavailable": "ప్రస్తుతం చాట్ ద్వారా ఆర్డర్ అందుబాటులో లేదు. యాప్‌లోని షాప్ నుండి ఆర్డర్ చేయవచ్చు.",
        "no_store": "మీ ఖాతా ఇంకా ఏ దుకాణంతోనూ అనుసంధానించబడలేదు, కాబట్టి ఇక్కడ ఆర్డర్ చేయలేను. దయచేసి మీ FlokIQ దుకాణాన్ని సంప్రదించండి.",
        "shop_unreachable": "ప్రస్తుతం దుకాణాన్ని చేరుకోలేకపోయాను. కొద్దిసేపటి తర్వాత మళ్ళీ ప్రయత్నించండి.",
        "not_found": "మీ దుకాణంలో '{query}' దొరకలేదు. దయచేసి వస్తువు యొక్క మరో పేరు చెప్పండి.",
        "choose": "మీ దుకాణంలో ఇవి దొరికాయి: {options}. మీకు ఏది కావాలి?",
        "ask_quantity": "ఒక్క {product} ధర ₹{price}. మీకు ఎన్ని కావాలి? గరిష్ఠంగా {max} ఆర్డర్ చేయవచ్చు.",
        "too_many": "ప్రస్తుతం {product} {available} మాత్రమే ఆర్డర్ చేయవచ్చు. మీకు ఎన్ని కావాలి?",
        "out_of_stock": "{product} ప్రస్తుతం స్టాక్‌లో లేదు. మీకు ఇంకేమైనా కావాలా?",
        "ask_address": "ఎక్కడ డెలివరీ చేయాలి? దయచేసి పూర్తి చిరునామా చెప్పండి.",
        "confirm": "{quantity} x {product} = ₹{total}. డెలివరీ చిరునామా: {address}. ఆర్డర్ చేయమంటారా?",
        "prescription": "ఈ వస్తువుకు పశువైద్యుని ప్రిస్క్రిప్షన్ అవసరం.",
        "batch_price": "వీటిలో కొన్ని వేరే ధర ఉన్న స్టాక్ నుండి వస్తాయి, కాబట్టి మొత్తం సరిగ్గా {quantity} x ₹{price} కాదు.",
        "what_to_change": "మీరు ఏమి మార్చాలనుకుంటున్నారు: వస్తువు, సంఖ్య లేదా చిరునామా?",
        "stock_changed": "{product} స్టాక్ లేదా ధర ఇప్పుడే మారింది. మీకు ఎన్ని కావాలి?",
        "placed": "మీ ఆర్డర్ {code} పూర్తయింది: {quantity} x {product}, ₹{total}. చెల్లింపు పూర్తి చేయడానికి Pay నొక్కండి.",
        "payment_retry": "మీ ఆర్డర్ సేవ్ అయింది, కానీ చెల్లింపు ప్రారంభం కాలేదు. మళ్ళీ ప్రయత్నించడానికి అవును అని చెప్పండి.",
        "order_failed": "ప్రస్తుతం ఆర్డర్ చేయలేకపోయాను. మళ్ళీ ప్రయత్నించడానికి అవును అని చెప్పండి, లేదా రద్దు చేయండి.",
        "cancelled": "సరే, రద్దు చేశాను. ఏమీ ఆర్డర్ కాలేదు.",
    },
    "kn": {
        "welcome": "ನೀವು ಯಾವ ವಸ್ತುವನ್ನು ಆರ್ಡರ್ ಮಾಡಲು ಬಯಸುತ್ತೀರಿ? ಅದರ ಹೆಸರು ಹೇಳಿ, ಉದಾ. ಔಷಧಿ, ಮೇವು ಅಥವಾ ಸಪ್ಲಿಮೆಂಟ್.",
        "unavailable": "ಈಗ ಚಾಟ್ ಮೂಲಕ ಆರ್ಡರ್ ಲಭ್ಯವಿಲ್ಲ. ಆ್ಯಪ್‌ನ ಶಾಪ್‌ನಿಂದ ಆರ್ಡರ್ ಮಾಡಬಹುದು.",
        "no_store": "ನಿಮ್ಮ ಖಾತೆ ಇನ್ನೂ ಯಾವುದೇ ಅಂಗಡಿಗೆ ಜೋಡಣೆಯಾಗಿಲ್ಲ, ಆದ್ದರಿಂದ ಇಲ್ಲಿ ಆರ್ಡರ್ ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ FlokIQ ಅಂಗಡಿಯನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "shop_unreachable": "ಈಗ ಅಂಗಡಿಯನ್ನು ಸಂಪರ್ಕಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "not_found": "ನಿಮ್ಮ ಅಂಗಡಿಯಲ್ಲಿ '{query}' ಸಿಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ವಸ್ತುವಿನ ಬೇರೆ ಹೆಸರು ಹೇಳಿ.",
        "choose": "ನಿಮ್ಮ ಅಂಗಡಿಯಲ್ಲಿ ಇವು ಸಿಕ್ಕವು: {options}. ನಿಮಗೆ ಯಾವುದು ಬೇಕು?",
        "ask_quantity": "ಒಂದು {product} ಬೆಲೆ ₹{price}. ನಿಮಗೆ ಎಷ್ಟು ಬೇಕು? ಗರಿಷ್ಠ {max} ಆರ್ಡರ್ ಮಾಡಬಹುದು.",
        "too_many": "ಈಗ {product} ಕೇವಲ {available} ಆರ್ಡರ್ ಮಾಡಬಹುದು. ನಿಮಗೆ ಎಷ್ಟು ಬೇಕು?",
        "out_of_stock": "{product} ಈಗ ಸ್ಟಾಕ್‌ನಲ್ಲಿ ಇಲ್ಲ. ನಿಮಗೆ ಬೇರೆ ಏನಾದರೂ ಬೇಕೇ?",
        "ask_address": "ಎಲ್ಲಿಗೆ ತಲುಪಿಸಬೇಕು? ದಯವಿಟ್ಟು ಪೂರ್ಣ ವಿಳಾಸ ಹೇಳಿ.",
        "confirm": "{quantity} x {product} = ₹{total}. ಡೆಲಿವರಿ ವಿಳಾಸ: {address}. ಆರ್ಡರ್ ಮಾಡಲೇ?",
        "prescription": "ಈ ವಸ್ತುವಿಗೆ ಪಶುವೈದ್ಯರ ಚೀಟಿ ಅಗತ್ಯ.",
        "batch_price": "ಇವುಗಳಲ್ಲಿ ಕೆಲವು ಬೇರೆ ಬೆಲೆಯ ಸ್ಟಾಕ್‌ನಿಂದ ಬರುತ್ತವೆ, ಆದ್ದರಿಂದ ಒಟ್ಟು ಮೊತ್ತ ನಿಖರವಾಗಿ {quantity} x ₹{price} ಅಲ್ಲ.",
        "what_to_change": "ನೀವು ಏನನ್ನು ಬದಲಾಯಿಸಲು ಬಯಸುತ್ತೀರಿ: ವಸ್ತು, ಸಂಖ್ಯೆ ಅಥವಾ ವಿಳಾಸ?",
        "stock_changed": "{product} ಸ್ಟಾಕ್ ಅಥವಾ ಬೆಲೆ ಈಗಷ್ಟೇ ಬದಲಾಗಿದೆ. ನಿಮಗೆ ಎಷ್ಟು ಬೇಕು?",
        "placed": "ನಿಮ್ಮ ಆರ್ಡರ್ {code} ಆಗಿದೆ: {quantity} x {product}, ₹{total}. ಪಾವತಿ ಪೂರ್ಣಗೊಳಿಸಲು Pay ಒತ್ತಿ.",
        "payment_retry": "ನಿಮ್ಮ ಆರ್ಡರ್ ಉಳಿಸಲಾಗಿದೆ, ಆದರೆ ಪಾವತಿ ಪ್ರಾರಂಭವಾಗಲಿಲ್ಲ. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಲು ಹೌದು ಎನ್ನಿ.",
        "order_failed": "ಈಗ ಆರ್ಡರ್ ಮಾಡಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಲು ಹೌದು ಎನ್ನಿ, ಅಥವಾ ರದ್ದು ಮಾಡಿ.",
        "cancelled": "ಸರಿ, ರದ್ದು ಮಾಡಿದೆ. ಏನೂ ಆರ್ಡರ್ ಆಗಿಲ್ಲ.",
    },
    "ml": {
        "welcome": "ഏത് സാധനമാണ് നിങ്ങൾ ഓർഡർ ചെയ്യാൻ ആഗ്രഹിക്കുന്നത്? അതിന്റെ പേര് പറയൂ, ഉദാ. മരുന്ന്, തീറ്റ അല്ലെങ്കിൽ സപ്ലിമെന്റ്.",
        "unavailable": "ഇപ്പോൾ ചാറ്റിലൂടെ ഓർഡർ ലഭ്യമല്ല. ആപ്പിലെ ഷോപ്പിൽ നിന്ന് ഓർഡർ ചെയ്യാം.",
        "no_store": "നിങ്ങളുടെ അക്കൗണ്ട് ഇതുവരെ ഒരു കടയുമായും ബന്ധിപ്പിച്ചിട്ടില്ല, അതിനാൽ ഇവിടെ ഓർഡർ ചെയ്യാൻ കഴിയില്ല. ദയവായി നിങ്ങളുടെ FlokIQ കടയുമായി ബന്ധപ്പെടുക.",
        "shop_unreachable": "ഇപ്പോൾ കടയുമായി ബന്ധപ്പെടാൻ കഴിഞ്ഞില്ല. കുറച്ച് കഴിഞ്ഞ് വീണ്ടും ശ്രമിക്കുക.",
        "not_found": "നിങ്ങളുടെ കടയിൽ '{query}' കണ്ടെത്തിയില്ല. ദയവായി സാധനത്തിന്റെ മറ്റൊരു പേര് പറയൂ.",
        "choose": "നിങ്ങളുടെ കടയിൽ ഇവ കണ്ടെത്തി: {options}. ഏതാണ് വേണ്ടത്?",
        "ask_quantity": "ഒരു {product} വില ₹{price}. എത്ര എണ്ണം വേണം? പരമാവധി {max} ഓർഡർ ചെയ്യാം.",
        "too_many": "ഇപ്പോൾ {product} {available} എണ്ണം മാത്രമേ ഓർഡർ ചെയ്യാൻ കഴിയൂ. എത്ര എണ്ണം വേണം?",
        "out_of_stock": "{product} ഇപ്പോൾ സ്റ്റോക്കിൽ ഇല്ല. മറ്റെന്തെങ്കിലും വേണോ?",
        "ask_address": "എവിടെയാണ് എത്തിക്കേണ്ടത്? ദയവായി മുഴുവൻ വിലാസം പറയൂ.",
        "confirm": "{quantity} x {product} = ₹{total}. ഡെലിവറി വിലാസം: {address}. ഓർഡർ ചെയ്യട്ടെ?",
        "prescription": "ഈ സാധനത്തിന് മൃഗഡോക്ടറുടെ കുറിപ്പടി ആവശ്യമാണ്.",
        "batch_price": "ഇവയിൽ ചിലത് വേറെ വിലയുള്ള സ്റ്റോക്കിൽ നിന്നാണ്, അതിനാൽ ആകെ തുക കൃത്യമായി {quantity} x ₹{price} അല്ല.",
        "what_to_change": "എന്താണ് മാറ്റേണ്ടത്: സാധനം, എണ്ണം അല്ലെങ്കിൽ വിലാസം?",
        "stock_changed": "{product} ന്റെ സ്റ്റോക്കോ വിലയോ ഇപ്പോൾ മാറി. എത്ര എണ്ണം വേണം?",
        "placed": "നിങ്ങളുടെ ഓർഡർ {code} ചെയ്തു: {quantity} x {product}, ₹{total}. പണമടയ്ക്കൽ പൂർത്തിയാക്കാൻ Pay അമർത്തുക.",
        "payment_retry": "നിങ്ങളുടെ ഓർഡർ സേവ് ചെയ്തു, പക്ഷേ പണമടയ്ക്കൽ ആരംഭിക്കാനായില്ല. വീണ്ടും ശ്രമിക്കാൻ അതെ എന്ന് പറയൂ.",
        "order_failed": "ഇപ്പോൾ ഓർഡർ ചെയ്യാൻ കഴിഞ്ഞില്ല. വീണ്ടും ശ്രമിക്കാൻ അതെ എന്ന് പറയൂ, അല്ലെങ്കിൽ റദ്ദാക്കൂ.",
        "cancelled": "ശരി, റദ്ദാക്കി. ഒന്നും ഓർഡർ ചെയ്തിട്ടില്ല.",
    },
}


class OrderSupervisor(DraftSupervisor):
    INTAKE_SUBDIR = "order_intakes"
    MESSAGES = _TEXT
    # Optional: text -> intent name, from the router's classifier (the chat
    # router sets it on default_supervisor). Asked only about a message the
    # order agent found nothing in. None (tests, other callers): not asked.
    topic_check: Optional[Callable[[str], str]] = None

    def _fresh(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "farmer_id": farmer_id,
            "language": language if language in SUPPORTED_LANGUAGES else "en-IN",
            "state": SEARCHING,
            # product: the chosen product as main_backend described it;
            # options: products offered for the farmer to pick from;
            # address: only an address the farmer gave here (otherwise
            # main_backend uses the farmer's profile address);
            # quote: main_backend's last quote, shown at CONFIRMING;
            # order: the created order, once placed.
            "draft": {"product": None, "options": [], "quantity": None, "address": None, "quote": None, "order": None},
            "transcript_history": [],
            "submitted": False,
        }

    # ------------------------------------------------------------------ helpers

    def _response(self, draft: dict[str, Any], text: str, input_transcript: Optional[str] = None,
                  include_audio: bool = True, options: Optional[dict] = None,
                  speech: Any = _UNSET) -> dict[str, Any]:
        language = draft["language"]
        speech_source = text if speech is _UNSET else speech
        if include_audio and speech_source:
            audio, audio_error = synthesize_speech(speech_source, target_lang=_lang(language))
        else:
            audio, audio_error = None, None
        resp: dict[str, Any] = {
            "session_id": draft["session_id"],
            "state": draft["state"],
            "language": language,
            "transcript": input_transcript,
            "draft": draft["draft"],
            "response_text": text,
            "response_audio_base64": b64encode(audio).decode("ascii") if audio else None,
            "audio_error": audio_error,
        }
        if options:
            resp["options"] = options
        if draft["state"] == ORDERED and draft["draft"].get("order"):
            # What the app needs to open the Razorpay checkout.
            resp["order"] = draft["draft"]["order"]
        return resp

    def _pills(self, language: str, choices: list[str], other_allowed: bool = True) -> dict[str, Any]:
        lang = _lang(language)
        return {"choices": choices, "other_label": _OTHER_LABEL.get(lang, "Other"), "other_allowed": other_allowed}

    def _quantity_pills(self, language: str, cap: int) -> dict[str, Any]:
        return self._pills(language, [str(q) for q in _QUANTITY_PILLS if q <= cap])

    def _confirm_pills(self, language: str) -> dict[str, Any]:
        yes, no = _YES_NO.get(_lang(language), _YES_NO["en"])
        return self._pills(language, [yes, no], other_allowed=True)

    def _cap(self, product: dict[str, Any]) -> int:
        try:
            available = int(product.get("available") or 0)
        except (TypeError, ValueError):
            available = 0
        return max(0, min(MAX_QUANTITY, available))

    def _extract(self, draft: dict[str, Any], text: str) -> dict[str, Any]:
        """One dedicated tool call per turn (same pattern as
        animal_registration). Never raises: on any failure it returns {}
        and the deterministic fallbacks in turn() still work (a tapped
        pill, a bare number, the reply_words yes/no/cancel lists)."""
        values = draft["draft"]
        state = draft["state"]
        known = []
        if values.get("product"):
            known.append(f"product: {values['product'].get('name')}")
        if values.get("quantity"):
            known.append(f"quantity: {values['quantity']}")
        asked = {
            SEARCHING: "which product they want",
            CHOOSING: "which of the OPTIONS they want",
            QUANTITY: "how many they want",
            ADDRESS: "the delivery address",
            CONFIRMING: "whether to place the order shown to them (yes/no), or to change something",
            CORRECTING: "what they want to change: the product, the quantity or the address",
        }.get(state, "which product they want")
        options = ""
        if state == CHOOSING and values.get("options"):
            numbered = ", ".join(f"{i}. {_choice_label(p)}" for i, p in enumerate(values["options"], start=1))
            options = f"\nOPTIONS: {numbered}"
        context = (
            f"Already known: {'; '.join(known) if known else 'nothing yet'}.\n"
            f"The farmer was just asked: {asked}.{options}\n"
            f"Farmer just said: \"{text}\""
        )
        try:
            adapter = BedrockTextAdapter(task=TaskTier.EXTRACTION)
            result = adapter.converse_with_tool(
                messages=[{"role": "user", "content": context}],
                tool_spec=_ORDER_TOOL_SPEC,
                system=_ORDER_SYSTEM,
                tool_choice_name="record_order_turn",
            )
            entities = dict(result.get("tool_input") or {})
        except Exception as exc:
            _log.warning("order extraction failed: %s", exc)
            return {}
        # The schema's own "no signal" value; left as a string it is truthy
        # and would hide the reply_words fallback (same fix as
        # animal_registration).
        if entities.get("confirmation_signal") == "none":
            entities["confirmation_signal"] = None
        return entities

    @staticmethod
    def _pill_signal(draft: dict[str, Any], text: str) -> Optional[str]:
        """'yes'/'no' when the reply is exactly one of the confirm pills this
        agent shows, so a tapped pill works even if the LLM gives no signal."""
        if draft["state"] != CONFIRMING:
            return None
        typed = " ".join((text or "").split()).lower()
        yes, no = _YES_NO.get(_lang(draft["language"]), _YES_NO["en"])
        if typed == yes.lower() or typed == _YES_NO["en"][0].lower():
            return "yes"
        if typed == no.lower() or typed == _YES_NO["en"][1].lower():
            return "no"
        return None

    @staticmethod
    def _as_quantity(value: Any) -> Optional[int]:
        """A positive whole number, or None. Rejects 0, negatives, fractions
        and anything that is not a number."""
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value > 0 else None
        if isinstance(value, float):
            return int(value) if value.is_integer() and value > 0 else None
        if isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
            return number if number > 0 else None
        return None

    def _pick_option(self, draft: dict[str, Any], text: str, entities: dict[str, Any]) -> Optional[dict[str, Any]]:
        """The option the farmer picked: a tapped pill (exact text), a bare
        option number, or the LLM's chosen_option."""
        options = draft["draft"].get("options") or []
        if not options:
            return None
        typed = " ".join((text or "").split()).lower()
        for product in options:
            if typed and typed in {_choice_label(product).lower(), str(product.get("name") or "").strip().lower()}:
                return product
        number = self._as_quantity(entities.get("chosen_option"))
        if number is None and draft["state"] == CHOOSING and typed.isdigit():
            number = int(typed)
        if number is not None and 1 <= number <= len(options):
            return options[number - 1]
        return None

    @staticmethod
    def _same_product(product: Optional[dict[str, Any]], query: str) -> bool:
        """True when a product_query only repeats the product already chosen
        (models sometimes echo it at the confirm step), so it must not
        restart the search."""
        if not product or not query:
            return False
        name = re.sub(r"\s+", " ", str(product.get("name") or "").lower()).strip()
        wanted = re.sub(r"\s+", " ", query.lower()).strip()
        return bool(name) and (wanted in name or name in wanted)

    def _end(self, draft: dict[str, Any], state: str, key: str, text: str, include_audio: bool) -> dict[str, Any]:
        """Close this conversation (CANCELLED or an unavailable shop) so the
        router stops sending the session's messages here."""
        draft["state"] = state
        draft["submitted"] = state == ORDERED
        self._save(draft)
        return self._response(draft, self._message(draft["language"], key), input_transcript=text,
                              include_audio=include_audio)

    # ------------------------------------------------------------------ steps

    def _search(self, draft: dict[str, Any], farmer_id: str, query: str, text: str,
                include_audio: bool) -> Optional[dict[str, Any]]:
        """Look the product up in the farmer's store. Returns a response to
        send now, or None when exactly one product matched and the flow can
        go on to the quantity in this same turn."""
        values = draft["draft"]
        language = draft["language"]
        found = flokiq_sync.search_products(farmer_id, query, limit=MAX_CHOICES)
        if found is None:
            self._save(draft)
            return self._response(draft, self._message(language, "shop_unreachable"), input_transcript=text,
                                  include_audio=include_audio)
        if not found["storeAssigned"]:
            return self._end(draft, CANCELLED, "no_store", text, include_audio)
        products = [
            _with_checked_image(p) for p in found["products"] if isinstance(p, dict) and p.get("productId")
        ][:MAX_CHOICES]
        _log.info("order search farmer=%s query=%r found=%d with_image=%d", farmer_id, query[:60], len(products),
                  sum(1 for p in products if p["image"]))
        if not products:
            values["product"] = None
            values["options"] = []
            draft["state"] = SEARCHING
            self._save(draft)
            return self._response(draft, self._message(language, "not_found", query=query), input_transcript=text,
                                  include_audio=include_audio)
        if len(products) == 1:
            values["product"] = products[0]
            values["options"] = []
            return None
        values["product"] = None
        values["options"] = products
        draft["state"] = CHOOSING
        self._save(draft)
        listed = ", ".join(f"{_choice_label(p)} ₹{_money(p.get('unitPrice'))}" for p in products)
        return self._response(
            draft, self._message(language, "choose", options=listed), input_transcript=text,
            include_audio=include_audio, options=self._pills(language, [_choice_label(p) for p in products]),
        )

    def _ask_quantity(self, draft: dict[str, Any], text: str, include_audio: bool,
                      key: str = "ask_quantity") -> dict[str, Any]:
        values = draft["draft"]
        product = values["product"]
        cap = self._cap(product)
        draft["state"] = QUANTITY
        values["quantity"] = None
        values["quote"] = None
        self._save(draft)
        message = self._message(draft["language"], key, product=product.get("name"), max=str(cap),
                                available=str(cap), price=_money(product.get("unitPrice")))
        return self._response(draft, message, input_transcript=text, include_audio=include_audio,
                              options=self._quantity_pills(draft["language"], cap))

    def _out_of_stock(self, draft: dict[str, Any], text: str, include_audio: bool) -> dict[str, Any]:
        values = draft["draft"]
        name = (values.get("product") or {}).get("name") or ""
        values.update({"product": None, "options": [], "quantity": None, "quote": None})
        draft["state"] = SEARCHING
        self._save(draft)
        return self._response(draft, self._message(draft["language"], "out_of_stock", product=name),
                              input_transcript=text, include_audio=include_audio)

    def _items(self, draft: dict[str, Any]) -> list[dict[str, Any]]:
        values = draft["draft"]
        return [{"productId": values["product"]["productId"], "quantity": values["quantity"]}]

    def _apply_problem(self, draft: dict[str, Any], body: dict[str, Any], text: str,
                       include_audio: bool) -> dict[str, Any]:
        """main_backend said the item cannot be ordered as asked (409)."""
        if body.get("reason") == "no_store":
            return self._end(draft, CANCELLED, "no_store", text, include_audio)
        problems = body.get("problems") if isinstance(body.get("problems"), list) else []
        problem = next((p for p in problems if isinstance(p, dict)), {})
        available = self._as_quantity(problem.get("available")) or 0
        if problem.get("reason") == "not_found" or available == 0:
            return self._out_of_stock(draft, text, include_audio)
        draft["draft"]["product"]["available"] = available
        return self._ask_quantity(draft, text, include_audio, key="too_many")

    def _quote(self, draft: dict[str, Any], farmer_id: str, text: str, include_audio: bool) -> dict[str, Any]:
        """Ask main_backend for the exact total and show it for confirmation."""
        values = draft["draft"]
        language = draft["language"]
        result = flokiq_sync.quote_order(farmer_id, self._items(draft), values.get("address") or "")
        status, body = result["status"], result["body"]
        if status == 409:
            return self._apply_problem(draft, body, text, include_audio)
        if status == 404 or status == 503:
            # Farmer unknown to main_backend, or ordering switched off there.
            return self._end(draft, CANCELLED, "unavailable", text, include_audio)
        if status != 200:
            self._save(draft)
            return self._response(draft, self._message(language, "shop_unreachable"), input_transcript=text,
                                  include_audio=include_audio)
        address = str(body.get("deliveryAddress") or "").strip()
        if not address:
            draft["state"] = ADDRESS
            values["quote"] = None
            self._save(draft)
            return self._response(draft, self._message(language, "ask_address"), input_transcript=text,
                                  include_audio=include_audio)
        values["quote"] = {
            "totalAmount": body.get("totalAmount"),
            "currency": body.get("currency") or "INR",
            "deliveryAddress": address,
        }
        draft["state"] = CONFIRMING
        self._save(draft)
        product = values["product"]
        message = self._message(
            language, "confirm", quantity=str(values["quantity"]), product=product.get("name"),
            total=_money(body.get("totalAmount")), address=address,
        )
        # "₹120 each" was said when asking how many; when the units come from
        # stock at different prices the total is not quantity x that price,
        # so say why before asking to confirm.
        price_varies = _price_varies(product.get("unitPrice"), values["quantity"], body.get("totalAmount"))
        if price_varies:
            note = self._message(language, "batch_price", quantity=str(values["quantity"]),
                                 price=_money(product.get("unitPrice")))
            message = f"{note} {message}"
        if product.get("prescriptionRequired"):
            message = f"{message} {self._message(language, 'prescription')}"
        _log.info("order quoted farmer=%s product=%s qty=%s total=%s price_varies=%s", farmer_id,
                  product.get("productId"), values["quantity"], body.get("totalAmount"), price_varies)
        return self._response(draft, message, input_transcript=text, include_audio=include_audio,
                              options=self._confirm_pills(language))

    def _place(self, draft: dict[str, Any], farmer_id: str, text: str, include_audio: bool) -> dict[str, Any]:
        """The farmer said yes to the quote: create the order in main_backend."""
        values = draft["draft"]
        language = draft["language"]
        address = (values.get("quote") or {}).get("deliveryAddress") or values.get("address") or ""
        result = flokiq_sync.create_order(farmer_id, self._items(draft), address)
        status, body = result["status"], result["body"]
        if status in (200, 201) and body.get("orderId") and isinstance(body.get("payment"), dict):
            product = values["product"]
            values["order"] = {
                "orderId": body["orderId"],
                "orderCode": body.get("orderCode"),
                "totalAmount": body.get("totalAmount"),
                "currency": body.get("currency") or "INR",
                "deliveryAddress": body.get("deliveryAddress") or address,
                "productName": product.get("name"),
                # Checked again here: a draft saved before photos were
                # checked, or with photos switched off since, must not pass
                # an unchecked value on.
                "image": _image_file(product.get("image")) if chat_order_images_enabled() else None,
                "quantity": values["quantity"],
                "payment": body["payment"],
            }
            draft["state"] = ORDERED
            draft["submitted"] = True
            self._save(draft)
            _log.info("order placed farmer=%s order=%s reused=%s total=%s image=%s", farmer_id, body["orderId"],
                      body.get("reused"), body.get("totalAmount"), bool(values["order"]["image"]))
            message = self._message(
                language, "placed", code=str(body.get("orderCode") or ""), quantity=str(values["quantity"]),
                product=product.get("name"), total=_money(body.get("totalAmount")),
            )
            return self._response(draft, message, input_transcript=text, include_audio=include_audio)
        reason = body.get("reason")
        if status == 409 and reason == "stock_changed":
            return self._ask_quantity(draft, text, include_audio, key="stock_changed")
        if status == 409:
            return self._apply_problem(draft, body, text, include_audio)
        if status == 422 and reason == "address_required":
            draft["state"] = ADDRESS
            values["quote"] = None
            self._save(draft)
            return self._response(draft, self._message(language, "ask_address"), input_transcript=text,
                                  include_audio=include_audio)
        if status == 404 or status == 503:
            return self._end(draft, CANCELLED, "unavailable", text, include_audio)
        # Payment could not start (502; main_backend kept the order and a
        # retry reuses it), or no answer at all: stay at CONFIRMING so "yes"
        # tries again.
        key = "payment_retry" if status == 502 else "order_failed"
        _log.warning("order not placed farmer=%s status=%s reason=%s", farmer_id, status, reason)
        draft["state"] = CONFIRMING
        self._save(draft)
        return self._response(draft, self._message(language, key), input_transcript=text,
                              include_audio=include_audio, options=self._confirm_pills(language))

    def _other_agent_topic(self, text: str) -> Optional[str]:
        """The other agent this message is about (one of RELEASE_TOPICS), or
        None. Never raises: if the classifier fails, the order goes on."""
        check = self.topic_check
        if check is None:
            return None
        try:
            intent = check(text)
        except Exception as exc:
            _log.warning("order topic check failed: %s", exc)
            return None
        return intent if intent in RELEASE_TOPICS else None

    # ------------------------------------------------------------------ turn

    def turn(self, farmer_id: str, session_id: str, text: str, language: str = "en-IN",
             include_audio: bool = True) -> dict[str, Any]:
        with self._session_lock(farmer_id, session_id):
            return self._turn_locked(farmer_id, session_id, text, language, include_audio)

    def _turn_locked(self, farmer_id: str, session_id: str, text: str, language: str,
                     include_audio: bool) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, language)
        if draft.get("submitted") or draft.get("state") == CANCELLED:
            # The last order on this session finished (placed or cancelled);
            # a new message starts a new one.
            draft = self._fresh(session_id, farmer_id, language)
        draft["language"] = language if language in SUPPORTED_LANGUAGES else draft["language"]
        draft["transcript_history"].append(text)

        if not chat_orders_enabled() or not flokiq_sync.orders_available(farmer_id):
            _log.info("order unavailable farmer=%s enabled=%s", farmer_id, chat_orders_enabled())
            return self._end(draft, CANCELLED, "unavailable", text, include_audio)

        entities = self._extract(draft, text)
        signal = (
            entities.get("confirmation_signal")
            or self._pill_signal(draft, text)
            or reply_words.confirmation_signal(text, draft["language"])
        )
        if signal == "cancel":
            _log.info("order cancelled farmer=%s state=%s", farmer_id, draft["state"])
            return self._end(draft, CANCELLED, "cancelled", text, include_audio)

        values = draft["draft"]
        state = draft["state"]
        changed = False
        previous_id = (values.get("product") or {}).get("productId")

        # 1) Product: a pick from the offered options, or a (new) product named.
        picked = self._pick_option(draft, text, entities) if state == CHOOSING else None
        query = str(entities.get("product_query") or "").strip()
        if picked:
            values["product"] = picked
            values["options"] = []
        elif query and not self._same_product(values.get("product"), query):
            reply = self._search(draft, farmer_id, query, text, include_audio)
            if reply is not None:
                return reply
        # Only a different product counts as a change -- a search that finds
        # the same product again (a reworded echo of it) must not undo the
        # farmer's "yes" at the confirm step.
        if (values.get("product") or {}).get("productId") != previous_id:
            changed = True

        # 2) Quantity: the LLM's reading, or a bare number when it was asked.
        quantity = self._as_quantity(entities.get("quantity"))
        if quantity is None and state == QUANTITY:
            quantity = self._as_quantity(text)
        # The LLM sometimes names the product but drops the number typed
        # next to it ("2 calcium gel"). Not while choosing (a bare number
        # there picks an option) nor at the address/confirm steps (a PIN
        # code, a house number).
        if quantity is None and state in (SEARCHING, QUANTITY, CORRECTING) and not entities.get("delivery_address"):
            quantity = _number_in_text(text)
        if quantity is not None and quantity != values.get("quantity"):
            values["quantity"] = quantity
            changed = True

        # 3) Address: the LLM's reading, or the whole reply when it was asked.
        address = str(entities.get("delivery_address") or "").strip()
        off_topic = bool(entities.get("off_topic"))
        if not address and state == ADDRESS and len(text.strip()) >= _MIN_ADDRESS_LENGTH and not signal and not off_topic:
            address = text.strip()
        if address and address != values.get("address"):
            values["address"] = address[:500]
            changed = True

        # A message about something else entirely (the weather, a sick
        # animal, a question about the herd) is let go instead of being
        # swallowed by the order flow: the unfinished order is closed and the
        # router sends the message to the right agent. Never for a message
        # that also carried anything for the order (a product, a pick, a
        # number, an address or a yes/no).
        nothing_for_order = not signal and not changed and quantity is None and not query and not picked and not address
        topic = None
        if nothing_for_order and not off_topic:
            # The LLM does not always flag it, so ask the router's
            # classifier too -- only for a message with nothing for the order.
            topic = self._other_agent_topic(text)
        if nothing_for_order and (off_topic or topic):
            _log.info("order released off-topic message farmer=%s state=%s topic=%s", farmer_id, state, topic)
            draft["state"] = CANCELLED
            self._save(draft)
            return {
                "session_id": draft["session_id"],
                "state": CANCELLED,
                "language": draft["language"],
                "released": True,
                "topic": topic,
                "response_text": "",
                "response_audio_base64": None,
                "audio_error": None,
            }

        product = values.get("product")
        if not product:
            if values.get("options"):
                # Still choosing: offer the same options again.
                draft["state"] = CHOOSING
                self._save(draft)
                listed = ", ".join(f"{_choice_label(p)} ₹{_money(p.get('unitPrice'))}" for p in values["options"])
                return self._response(
                    draft, self._message(draft["language"], "choose", options=listed), input_transcript=text,
                    include_audio=include_audio,
                    options=self._pills(draft["language"], [_choice_label(p) for p in values["options"]]),
                )
            draft["state"] = SEARCHING
            self._save(draft)
            return self._response(draft, self._message(draft["language"], "welcome"), input_transcript=text,
                                  include_audio=include_audio)

        cap = self._cap(product)
        if cap == 0:
            return self._out_of_stock(draft, text, include_audio)
        if not values.get("quantity"):
            return self._ask_quantity(draft, text, include_audio)
        if values["quantity"] > cap:
            key = "too_many" if cap < MAX_QUANTITY else "ask_quantity"
            return self._ask_quantity(draft, text, include_audio, key=key)

        # Place only when the farmer agreed to the quote that is on screen:
        # a "yes" that also changes something ("yes, but make it 3") gets a
        # fresh quote first.
        if state == CONFIRMING and signal == "yes" and not changed and values.get("quote"):
            return self._place(draft, farmer_id, text, include_audio)
        if state == CONFIRMING and signal == "no" and not changed:
            draft["state"] = CORRECTING
            self._save(draft)
            return self._response(draft, self._message(draft["language"], "what_to_change"), input_transcript=text,
                                  include_audio=include_audio)
        if state == CORRECTING and not changed:
            self._save(draft)
            return self._response(draft, self._message(draft["language"], "what_to_change"), input_transcript=text,
                                  include_audio=include_audio)
        if state == ADDRESS and not values.get("address"):
            self._save(draft)
            return self._response(draft, self._message(draft["language"], "ask_address"), input_transcript=text,
                                  include_audio=include_audio)
        return self._quote(draft, farmer_id, text, include_audio)
