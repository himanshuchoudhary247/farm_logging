"""Placeholder agent used until real photo agents exist.

No model call and no cost. It tells the farmer honestly, in their language,
that the photo arrived and that answers from photos are coming, and what to
do meanwhile. It never makes up a count, weight or diagnosis: if it is ever
switched on in production by mistake, the farmer still reads only the truth.
"""
from __future__ import annotations

from services.image_agent.base import ImageRequest, ImageResult

_MESSAGES = {
    "en": "Photo received. Answers from photos are coming soon. For now, please describe it in words and I will help.",
    "hi": "फोटो मिल गई। फोटो से जवाब देने की सुविधा जल्द आ रही है। अभी के लिए कृपया शब्दों में बताइए, मैं मदद करूँगा।",
    "mr": "फोटो मिळाला. फोटोवरून उत्तर देण्याची सुविधा लवकरच येत आहे. सध्या कृपया शब्दांत सांगा, मी मदत करेन.",
    "ta": "புகைப்படம் கிடைத்தது. புகைப்படத்திலிருந்து பதில் சொல்லும் வசதி விரைவில் வருகிறது. இப்போதைக்கு வார்த்தைகளில் சொல்லுங்கள், நான் உதவுகிறேன்.",
    "te": "ఫోటో అందింది. ఫోటో నుండి సమాధానం చెప్పే సదుపాయం త్వరలో వస్తుంది. ప్రస్తుతానికి మాటల్లో చెప్పండి, నేను సహాయం చేస్తాను.",
    "kn": "ಫೋಟೋ ಸಿಕ್ಕಿದೆ. ಫೋಟೋದಿಂದ ಉತ್ತರ ನೀಡುವ ಸೌಲಭ್ಯ ಶೀಘ್ರದಲ್ಲೇ ಬರಲಿದೆ. ಸದ್ಯಕ್ಕೆ ದಯವಿಟ್ಟು ಮಾತಿನಲ್ಲಿ ತಿಳಿಸಿ, ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ.",
    "ml": "ഫോട്ടോ കിട്ടി. ഫോട്ടോയിൽ നിന്ന് മറുപടി നൽകുന്ന സൗകര്യം ഉടൻ വരുന്നു. ഇപ്പോൾ വാക്കുകളിൽ പറയൂ, ഞാൻ സഹായിക്കാം.",
}


class StubImageAgent:
    name = "stub"

    def analyze(self, request: ImageRequest) -> ImageResult:
        lang = (request.language or "en").split("-", 1)[0].lower()
        return ImageResult(reply_text=_MESSAGES.get(lang, _MESSAGES["en"]), data={})
