import os
import requests

def download_font():
    font_dir = "fonts"
    if not os.path.exists(font_dir):
        os.makedirs(font_dir)

    # Use the raw file from Google Fonts GitHub repository
    # Using a specific commit hash or checking the latest structure usually works better than main which might change
    # But for now, let's try the standard path.
    url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP-Regular.ttf"
    target_path = os.path.join(font_dir, "NotoSansJP-Regular.ttf")

    print(f"Downloading font from {url}...")
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(target_path, 'wb') as f:
                f.write(response.content)
            print(f"Successfully downloaded to {target_path}")
            print(f"File size: {os.path.getsize(target_path)} bytes")
        else:
            print(f"Failed to download. Status code: {response.status_code}")
            
    except Exception as e:
        print(f"Error downloading font: {e}")

if __name__ == "__main__":
    download_font()
