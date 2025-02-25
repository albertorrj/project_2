from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, send_from_directory
from werkzeug.utils import secure_filename
from google.cloud import speech
from google.protobuf import wrappers_pb2
from google.cloud import texttospeech_v1
import os
#Added for Sentiment
from google.cloud import language_v2

sr_client=speech.SpeechClient()
tts_client = texttospeech_v1.TextToSpeechClient()
sa_client = language_v2.LanguageServiceClient()

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
TTS_FOLDER = 'tts'
ALLOWED_EXTENSIONS = {'wav'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TTS_FOLDER'] = TTS_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TTS_FOLDER, exist_ok=True)

def sample_analyze_sentiment(text_file):
    # Available types: PLAIN_TEXT, HTML
    document_type_in_plain_text = language_v2.Document.Type.PLAIN_TEXT

    # Optional. If not specified, the language is automatically detected.
    # For list of supported languages:
    # https://cloud.google.com/natural-language/docs/languages
    language_code = "en"
    document = {
        #"content": text_content,
        "content": text_file,
        "type_": document_type_in_plain_text,
        "language_code": language_code,
    }

    # Available values: NONE, UTF8, UTF16, UTF32
    # See https://cloud.google.com/natural-language/docs/reference/rest/v2/EncodingType.
    encoding_type = language_v2.EncodingType.UTF8

    response = sa_client.analyze_sentiment(
        request={"document": document, "encoding_type": encoding_type}
    )

    return response

def sample_synthesize_speech(text=None, ssml=None):
    input = texttospeech_v1.SynthesisInput()
    if ssml:
      input.ssml = ssml
    else:
      input.text = text

    voice = texttospeech_v1.VoiceSelectionParams()
    voice.language_code = "en-UK"
    #voice.language_code = "en-AU"
    # voice.ssml_gender = "MALE"

    audio_config = texttospeech_v1.AudioConfig()
    audio_config.audio_encoding = "LINEAR16"

    request = texttospeech_v1.SynthesizeSpeechRequest(
        input=input,
        voice=voice,
        audio_config=audio_config,
    )

    response = tts_client.synthesize_speech(request=request)

    return response.audio_content


def sample_recognize(content):
  audio=speech.RecognitionAudio(content=content)

  config=speech.RecognitionConfig(
  # encoding=speech.RecognitionConfig.AudioEncoding.MP3,
  # sample_rate_hertz=24000,
  language_code="en-US",
  model="latest_long",
  audio_channel_count=1,
  enable_word_confidence=True,
  enable_word_time_offsets=True,
  )

  operation=sr_client.long_running_recognize(config=config, audio=audio)

  response=operation.result(timeout=90)

  txt = ''
  for result in response.results:
    txt = txt + result.alternatives[0].transcript + '\n'

  return txt

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_files(folder):
    files = []
    for filename in os.listdir(folder):
    #for filename in os.listdir(UPLOAD_FOLDER):
        if allowed_file(filename):
            files.append(filename)
            print(filename)
    files.sort(reverse=True)
    return files

@app.route('/')
def index():
    files = get_files(app.config['UPLOAD_FOLDER'])
    tts_files = get_files(app.config['TTS_FOLDER'])

    return render_template('index.html', files=files, tts_files=tts_files)

@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'audio_data' not in request.files:
        flash('No audio data')
        return redirect(request.url)
    file = request.files['audio_data']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    if file:
        # filename = secure_filename(file.filename)
        filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        #
        # Modify this block to call the speech to text API
        # Save transcript to same filename but .txt
        #
 
        f = open(file_path,'rb')
        data = f.read()
        f.close()

        text = sample_recognize(data)

        #Modified the text file for the sentiment analysis

        # Create text file path
        text_file_path = file_path + '.txt'

        # Save file
        with open(text_file_path, 'w') as text_file:
            text_file.write(text)
#        print(text)
#        text_path = open(file_path+'.txt','w')
#        f.write(text)
#        f.close()

    # Analyze sentiment and append to file
    sentiment = sample_analyze_sentiment(text)
    score = sentiment.document_sentiment.score * sentiment.document_sentiment.magnitude
    sentiment_category = "POSITIVE" if score > 0.75 else "NEGATIVE" if score < -0.75 else "NEUTRAL"

    with open(text_file_path, 'a') as f:
        f.write("\n\n--- Sentiment Analysis ---\n")
        f.write(f"Sentiment Score: {score:.2f}\n")
        f.write(f"Sentiment: {sentiment_category}\n")

    print(f"Sentiment analysis saved for: {text_file_path}")    

    return redirect('/') 

@app.route('/upload/<filename>')
def get_file(filename):
    return send_file(filename)

    
@app.route('/upload_text', methods=['POST'])
def upload_text():
    text = request.form['text']
    print(text)
    #
    # Modify this block to call the stext to speech API
    #

    wav = sample_synthesize_speech(text)

    filename = 'tts_' +datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
    audio_path = os.path.join(app.config['TTS_FOLDER'], filename)
    
    # save audio
    f = open(audio_path,'wb')
    f.write(wav)
    f.close()

    #save text
    text_file_path = audio_path + '.txt'

    # Save text to file
    with open(text_file_path, 'w') as text_file:
        text_file.write(text)

    # Analyze sentiment and append results
    sentiment = sample_analyze_sentiment(text)
    score = sentiment.document_sentiment.score * sentiment.document_sentiment.magnitude
    sentiment_category = "POSITIVE" if score > 0.75 else "NEGATIVE" if score < -0.75 else "NEUTRAL"

    with open(text_file_path, 'a') as f:
        f.write("\n\n--- Sentiment Analysis ---\n")
        f.write(f"Sentiment Score: {score:.2f}\n")
        f.write(f"Sentiment: {sentiment_category}\n")

    print(f"Sentiment analysis saved for: {text_file_path}")
#    f = open(audio_path+'.txt','w')
#    f.write(text)
#    f.close()

    return redirect('/') 

@app.route('/script.js',methods=['GET'])
def scripts_js():
    return send_file('./script.js')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    if os.path.exists(os.path.join(app.config['TTS_FOLDER'], filename)):
        folder = app.config['TTS_FOLDER']
    else:
        folder = app.config['UPLOAD_FOLDER']
    return send_from_directory(folder, filename)

if __name__ == '__main__':
    app.run(debug=True)