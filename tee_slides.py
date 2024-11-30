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

def parse_arguments():
    parser = argparse.ArgumentParser(description='Smart Tee Slides Application')
    parser.add_argument('directory', type=str, nargs='?', default=os.getcwd(), help='Target directory for saving slides (default: current working directory)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose debugging')
    parser.add_argument('-s', '--sensitivity', type=int, default=5, help='Sensitivity for change detection (1-10)')
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

def main():
    args = parse_arguments()
    setup_logging(args.verbose)
    ensure_slide_directory(args.directory)

    previous_hash = None
    sensitivity = args.sensitivity

    for line in sys.stdin:
        try:
            # Pass all messages through
            print(line, end='', flush=True)
            
            message = json.loads(line)
            if message.get("type") != "stream.image.snapshot":
                continue
            
            image_data = base64.b64decode(message.get("data"))
            image = Image.open(BytesIO(image_data)).convert('RGB')
            current_hash = imagehash.average_hash(image)

            if previous_hash is None:
                logging.debug("First image received. Saving as initial slide.")
                save_image(image, args.directory)
                previous_hash = current_hash
                continue

            difference = previous_hash - current_hash
            logging.debug(f"Hash difference: {difference}")

            if difference >= sensitivity:
                logging.info(f"Significant change detected (diff={difference}). Saving new slide.")
                save_image(image, args.directory)
                previous_hash = current_hash
            else:
                logging.debug("No significant change detected.")

        except json.JSONDecodeError:
            logging.error("Failed to decode JSON from input.")
        except base64.binascii.Error:
            logging.error("Failed to decode base64 image data.")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
