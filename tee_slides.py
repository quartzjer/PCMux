import sys
import json
import base64
import os
import argparse
import logging
from datetime import datetime
from io import BytesIO

from PIL import Image
import imagehash
import google.generativeai as genai

def parse_arguments():
    parser = argparse.ArgumentParser(description='Smart Tee Slides Application')
    parser.add_argument('directory', type=str, nargs='?', default=os.getcwd(), help='Target directory for saving slides (default: current working directory)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose debugging')
    parser.add_argument('-s', '--sensitivity', type=int, default=5, help='Sensitivity for change detection (1-10)')
    parser.add_argument('-g', '--gemini', action='store_true', help='Enable Gemini API for enhanced slide change detection')
    return parser.parse_args()

def setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr)

def ensure_slide_directory(directory):
    os.makedirs(directory, exist_ok=True)

def save_image(image, directory):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    filepath = os.path.join(directory, f'{timestamp}.png')
    image.save(filepath)
    logging.info(f"Saved slide: {filepath}")

def upload_to_gemini(image):
    image_bytes = BytesIO()
    image.save(image_bytes, format='PNG')
    image_bytes = image_bytes.getvalue()

    file = genai.upload_file_bytes(image_bytes, mime_type='image/png')
    return file.uri

def use_gemini_for_comparison(prev_image, curr_image, prompt):
    prev_image_uri = upload_to_gemini(prev_image)
    curr_image_uri = upload_to_gemini(curr_image)

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash-8b",
        generation_config={
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        },
        system_instruction=prompt,
    )

    chat_session = model.start_chat()
    response = chat_session.send_message([prev_image_uri, curr_image_uri])

    logging.debug(f"Gemini API response: {response.text}")

    if "<decision>" in response.text:
        decision_section = response.text.split("<decision>")[1].split("</decision>")[0].strip()
        if "SAVE" in decision_section:
            return True
    return False

def main():
    args = parse_arguments()
    setup_logging(args.verbose)
    ensure_slide_directory(args.directory)

    previous_hash = None
    previous_image = None
    sensitivity = args.sensitivity

    if args.use_gemini:
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        with open('tee_slides.txt', 'r') as prompt_file:
            gemini_prompt = prompt_file.read()
        logging.debug("Gemini API enabled for enhanced slide detection.")

    for line in sys.stdin:
        try:
            # Pass all messages through
            print(line, end='', flush=True)
            
            message = json.loads(line)
            if message.get("type") != "pcmux.video.frame":
                continue
            
            image_data = base64.b64decode(message.get("data"))
            image = Image.open(BytesIO(image_data)).convert('RGB')
            current_hash = imagehash.average_hash(image)

            if previous_hash is None:
                logging.debug("First image received. Saving as initial slide.")
                save_image(image, args.directory)
                previous_hash = current_hash
                if args.use_gemini:
                    previous_image = image
                continue

            difference = previous_hash - current_hash
            logging.debug(f"Hash difference: {difference}")

            if difference >= sensitivity:
                logging.info(f"Significant hash change detected (diff={difference}).")
                save_slide = True

                if args.use_gemini:
                    logging.debug("Using Gemini API for additional check.")
                    gemini_decision = use_gemini_for_comparison(previous_image, image, gemini_prompt)
                    if gemini_decision:
                        logging.info("Gemini API decision: SAVE")
                    else:
                        logging.info("Gemini API decision: SKIP")
                    save_slide = gemini_decision

                if save_slide:
                    logging.info("Saving new slide.")
                    save_image(image, args.directory)
                    previous_hash = current_hash
                    if args.use_gemini:
                        previous_image = image
                else:
                    logging.debug("Decided not to save the slide.")
            else:
                logging.debug("No significant hash change detected.")

        except json.JSONDecodeError:
            logging.error("Failed to decode JSON from input.")
        except base64.binascii.Error:
            logging.error("Failed to decode base64 image data.")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
