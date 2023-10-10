from flask import Flask, request, render_template_string
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont
import requests
import json
import os
import re
import string
import base64
from io import BytesIO
from bidi.algorithm import get_display
import arabic_reshaper

app = Flask(__name__, static_url_path='/static')

# Updated font paths to be in the same directory as this script.
FONTS = {
    "he": {
        "Horev": "./Horev.ttf",
        "MiriamMonoCLM-Book": "./MiriamMonoCLM-Book.ttf",
        "VarelaRound-Regular": "./VarelaRound-Regular.ttf"
    },
    "ar": {
        "Majeed": "./Majeed.ttf"
    }
}


def get_quranic_text(ref):
    url = f'http://api.alquran.cloud/v1/ayah/{ref}'
    response = requests.get(url=url)
    data = json.loads(response.text)
    return data['data']['text']

def get_sefaria_text(ref):
    url = f'https://www.sefaria.org/api/texts/{ref}?context=0'
    response = requests.get(url=url)
    data = json.loads(response.text)
    text_list = data['he']
    text = ' '.join(text_list)
    text = text.replace(u"\u05BE", " ")
    exclude = set(string.punctuation + u"\uFEFF" + "\n")
    text = ''.join(char for char in text if char not in exclude)
    strip_cantillation_vowel_regex = re.compile(r"[^\u05d0-\u05f4\s]", re.UNICODE)
    text = strip_cantillation_vowel_regex.sub('', text)
    return text

def generate_micrography(source, text_ref, image, sampleDensity, language, fontName, transparentText, customText=None):
    imgBgColor = (120, 120, 120)  # rgb
    fontSize = 10
    fontDrawSize = 18
    font = ImageFont.truetype(FONTS[language][fontName], fontDrawSize)
    imgMargin = 10
    sample = image
    width, height = sample.size
    if width > height:
        basewidth = 330
        wpercent = basewidth / float(sample.size[0])
        hsize = int((float(sample.size[1])*float(wpercent)))
        sample = sample.resize((basewidth, hsize), Image.LANCZOS)
        width, height = sample.size
    else:
        baseheight = 300
        hpercent = baseheight / float(sample.size[1])
        wsize = int((float(sample.size[0])*float(hpercent)))
        sample = sample.resize((wsize, baseheight), Image.LANCZOS)
        width, height = sample.size

    if source == 'quran':
        text = get_quranic_text(text_ref)
    elif source == 'sefaria':
        text = get_sefaria_text(text_ref)
    elif source == 'custom':
        text = customText
    else:
        raise ValueError('Invalid text source.')

    if language == 'ar':
        text = text[::-1]  # Reverse the text first
        reshaped_text = arabic_reshaper.reshape(text)  # Then reshape
        text = get_display(reshaped_text)

    outputImageSize = (width * fontSize // sampleDensity + imgMargin, height * fontSize // sampleDensity + imgMargin)
    outputImage = Image.new("RGB", outputImageSize, color=imgBgColor)
    draw = ImageDraw.Draw(outputImage)
    index = 0

    if language == 'he':
        # Hebrew rendering loop
        for y in range(0, height, sampleDensity):
            for x in range(width - 1, -1, -sampleDensity):
                color = sample.getpixel((x, y))
                if color == (255, 255, 255):
                    color = (0, 0, 0)
                try:
                    draw.text((x * fontSize // sampleDensity, y * fontSize // sampleDensity), text[index], font=font, fill=color)
                    index += 1
                except IndexError:
                    index = 0
    else:  # Arabic
        # Arabic rendering loop
        for y in range(0, height, sampleDensity):
            for x in range(width - 1, -1, -sampleDensity):
                color = sample.getpixel((x, y))
                if color == (255, 255, 255):
                    color = (0, 0, 0)
                try:
                    draw.text((x * fontSize // sampleDensity, y * fontSize // sampleDensity), text[index], font=font, fill=color)
                    index += 1
                except IndexError:
                    index = 0

    buffered = BytesIO()
    outputImage.save(buffered, format="JPEG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return f"data:image/jpeg;base64,{img_str}", text


@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files['file']
        text_ref = request.form['textRef']
        source = request.form['source']
        sampleDensity = int(request.form['sampleDensity'])
        language = request.form['language']
        fontName = request.form['font']
        transparentText = request.form['transparentText']
        customText = request.form.get('customText', None)

        filename = secure_filename(file.filename)
        UPLOADS_DIR = './uploads'
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        filepath = os.path.join(UPLOADS_DIR, filename)
        file.save(filepath)

        image = Image.open(filepath)
        result, text = generate_micrography(source, text_ref, image, sampleDensity, language, fontName, transparentText, customText)
        
        os.remove(filepath)
        
        return render_template_string("<p>Text used in the micrography: {{text}}</p><img src='{{result}}'>", text=text, result=result)
    else:
        sample_input_img_url = url_for('static', filename='sample_input.jpg')
        sample_output_img_url = url_for('static', filename='sample_output.jpg')
        return f'''
        <!doctype html>
        <title>Upload File and Text Reference</title>
        <h1>Upload File and Text Reference</h1>
        <h2>Sample Input Image</h2>
        <img src="{sample_input_img_url}" alt="Sample Input">
        <h2>Sample Output Image</h2>
        <img src="{sample_output_img_url}" alt="Sample Output">
        <form method="post" enctype="multipart/form-data">
            <label for="file">Upload Image:</label><br>
            <input type="file" name="file"><br>
            <label for="source">Choose a source:</label><br>
            <input type="radio" id="quran" name="source" value="quran">
            <label for="quran">Quran (Example: '2:255')</label><br>
            <input type="radio" id="sefaria" name="source" value="sefaria">
            <label for="sefaria">Sefaria (Example: 'Genesis 1')</label><br>
            <input type="radio" id="custom" name="source" value="custom">
            <label for="custom">Custom Text</label><br>
            <label for="textRef">Enter Text Reference:</label><br>
            <input type="text" name="textRef"><br>
            <label for="customText">Enter Custom Text:</label><br>
            <input type="text" name="customText"><br>
            <label for="sampleDensity">Sample Density:</label><br>
            <input type="number" name="sampleDensity" value="5"><br>
            <label for="language">Choose a language:</label><br>
            <input type="radio" id="he" name="language" value="he">
            <label for="he">Hebrew</label><br>
            <input type="radio" id="ar" name="language" value="ar">
            <label for="ar">Arabic</label><br>
            <label for="font">Choose a font:</label><br>
            <input type="radio" id="Horev" name="font" value="Horev">
            <label for="Horev">Horev (Hebrew)</label><br>
            <input type="radio" id="MiriamMonoCLM-Book" name="font" value="MiriamMonoCLM-Book">
            <label for="MiriamMonoCLM-Book">MiriamMonoCLM-Book (Hebrew)</label><br>
            <input type="radio" id="VarelaRound-Regular" name="font" value="VarelaRound-Regular">
            <label for="VarelaRound-Regular">VarelaRound-Regular (Hebrew)</label><br>
            <input type="radio" id="Majeed" name="font" value="Majeed">
            <label for="Majeed">Majeed (Arabic)</label><br>
            <label for="transparentText">Transparent Text:</label><br>
            <input type="radio" id="on" name="transparentText" value="on">
            <label for="on">On</label><br>
            <input type="radio" id="off" name="transparentText" value="off">
            <label for="off">Off</label><br>
            <input type="submit" value="Upload">
        </form>
        '''
        
if __name__ == '__main__':
    app.run(debug=True, port=5002)
