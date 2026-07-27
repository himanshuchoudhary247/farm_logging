"""Voice capture page - standalone HTML served via Streamlit static files."""
import os
import streamlit as st

st.set_page_config(page_title="Voice Capture", page_icon="🎤", layout="centered")

st.title("🎤 Voice Capture")
st.caption("Speak clearly, then click Submit to send your text back to the form.")

VOICE_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice Capture</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; background: #f8f9fa; }
  h1 { text-align: center; }
  select, button { padding: 10px 20px; font-size: 16px; border-radius: 12px; border: 2px solid #ddd; }
  #mic-btn { background: #ff4b4b; color: white; cursor: pointer; font-weight: 600; }
  #mic-btn:hover { background: #e03e3e; }
  #mic-btn.recording { animation: pulse 1s infinite; background: #cc0000; }
  @keyframes pulse { 0%,100%{box-shadow:0 0 0 0 rgba(255,0,0,0.4)} 50%{box-shadow:0 0 0 10px rgba(255,0,0,0)} }
  #status { margin: 10px 0; font-size: 14px; color: #666; }
  #transcript { width: 100%; min-height: 120px; border: 2px solid #ddd; border-radius: 12px; padding: 12px; font-size: 16px; margin: 10px 0; resize: vertical; }
  .row { display: flex; gap: 10px; align-items: center; margin: 10px 0; }
  .final { color: #111; font-weight: 500; }
  .interim { color: #999; font-style: italic; }
  #submit-btn { background: #28a745; color: white; font-size: 18px; width: 100%; padding: 14px; cursor: pointer; font-weight: 600; border: none; border-radius: 12px; margin-top: 10px; }
  #submit-btn:hover { background: #218838; }
  #submit-btn:disabled { background: #ccc; cursor: not-allowed; }
</style>
</head>
<body>
<h1>🎤 Voice Capture</h1>
<div class="row">
  <select id="lang">
    <option value="en-US">English</option>
    <option value="hi-IN">Hindi</option>
    <option value="kn-IN">Kannada</option>
    <option value="te-IN">Telugu</option>
    <option value="ta-IN">Tamil</option>
    <option value="mr-IN">Marathi</option>
    <option value="pa-IN">Punjabi</option>
  </select>
  <button id="mic-btn" onclick="toggleMic()">🎤 Start Recording</button>
</div>
<div id="status"></div>
<textarea id="transcript" placeholder="Your speech will appear here... You can also type directly."></textarea>
<button id="submit-btn" onclick="submitText()">✅ Send to Form</button>

<script>
var rec = null, finalT = '';
function toggleMic() {
  if (rec) { rec.stop(); return; }
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { document.getElementById('status').textContent = '⚠️ Voice not supported. Type your message below.'; return; }
  rec = new SR();
  rec.lang = document.getElementById('lang').value;
  rec.interimResults = true;
  rec.continuous = true;
  rec.onstart = function() {
    document.getElementById('mic-btn').textContent = '🔴 Stop Recording';
    document.getElementById('mic-btn').classList.add('recording');
    document.getElementById('status').textContent = '🎧 Listening... Speak now';
    finalT = '';
  };
  rec.onresult = function(e) {
    var interim = '';
    for (var i = e.resultIndex; i < e.results.length; i++) {
      var t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalT += t + ' '; else interim += t;
    }
    document.getElementById('transcript').value = finalT + interim;
  };
  rec.onend = function() {
    document.getElementById('mic-btn').textContent = '🎤 Start Recording';
    document.getElementById('mic-btn').classList.remove('recording');
    rec = null;
    document.getElementById('transcript').value = finalT.trim();
    document.getElementById('status').textContent = finalT.trim() ? '✅ Done! Click "Send to Form" below.' : 'No speech detected. Try again or type below.';
  };
  rec.onerror = function(e) {
    document.getElementById('mic-btn').textContent = '🎤 Start Recording';
    document.getElementById('mic-btn').classList.remove('recording');
    rec = null;
    document.getElementById('status').textContent = 'Error: ' + e.error + '. Try again or type below.';
  };
  rec.start();
}
function submitText() {
  var text = document.getElementById('transcript').value.trim();
  if (!text) { alert('Please speak or type something first!'); return; }
  window.location.href = '/voice_done?text=' + encodeURIComponent(text);
}
</script>
</body>
</html>
"""

st.components.v1.html(VOICE_PAGE, height=520, scrolling=True)
