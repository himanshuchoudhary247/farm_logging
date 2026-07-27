import streamlit.components.v1 as components
import os

_component_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "frontend")
voice_component = components.declare_component("voice_component", path=_component_dir)


def voice_input(label="🎤 Speak", key=None, lang="en-US", height=120):
    """Render a voice input button using Web Speech API.

    Returns the transcribed text when the user stops speaking.
    """
    return voice_component(label=label, lang=lang, key=key, default="", height=height)
