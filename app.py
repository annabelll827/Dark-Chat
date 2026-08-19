from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import os
import uuid # بۆ دروستکردنی ناوی یونیک بۆ فایلەکان
import tempfile # بۆ بەڕێوەبردنی فایلە کاتییەکان

app = Flask(__name__)
CORS(app) # Allow cross-origin requests from your frontend

# دروستکردنی دایرێکتۆری کاتی بۆ وێنە بەرزکراوەکان ئەگەر نەبوو
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'uploaded_images_osint')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

class ImageAccountFinder:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        self.platforms = [
            'facebook.com', 'instagram.com', 'tiktok.com', 
            'twitter.com', 'x.com', 'linkedin.com', 'pinterest.com'
        ]

    def search_local_image(self, file_path):
        if not os.path.exists(file_path):
            print(f"[-] هەڵە: وێنەکە لەم شوێنەدا نەدۆزرایەوە: {file_path}")
            return []

        print(f"[*] خەریکی بەرزکردنەوە و گەڕانی وێنەیە: {file_path}...")
        
        # بەکارهێنانی Yandex Images چونکە بۆ وێنەی ناوخۆیی زۆر بەهێزە
        # تێبینی: ئەم URLـە لەوانەیە بگۆڕێت بە تێپەڕبوونی کات لەلایەن Yandexـەوە.
        # بەردەوام پێویستی بە پشکنین و نوێکردنەوە دەبێت.
        search_upload_url = 'https://yandex.com/images-apphost/image-download?cbird=37&images_avatars_size=tycoon&find_image_page_url=https%3A%2F%2Fyandex.com%2Fimages%2F&can_retry=1'
        
        try:
            with open(file_path, 'rb') as f:
                # دیاریکردنی ناوی فایلەکە و جۆرەکەی بۆ ناردن
                files = {'upfile': (os.path.basename(file_path), f, 'image/jpeg')} # وێنەکان زۆرجار وەک jpeg بەرز دەکرێنەوە
                
                # یەکەم هەنگاو: بەرزکردنەوەی وێنەکە بۆ یاندێکس
                print("[*] بەرزکردنەوەی وێنەکە بۆ Yandex...")
                response = requests.post(search_upload_url, headers=self.headers, files=files, timeout=30) # زیادکردنی کاتی چاوەڕوانی
                
            if response.status_code == 200:
                result_json = response.json()
                cbir_id = result_json.get('cbir_id') # ناسنامەی وێنەکە لە یاندێکس
                if not cbir_id:
                    print("[-] نەتوانرا ناسنامەی وێنەکە لە سێرڤەر وەربگیرێت.")
                    print(f"       وەڵامی یاندێکس: {response.text}")
                    return []
                
                # URLـی ئەنجامی گەڕانەکە لە یاندێکس
                final_search_url = f"https://yandex.com/images/search?rpt=imageview&cbir_id={cbir_id}"
                print(f"[*] گەڕان بەدوای ئەنجامەکاندا لە: {final_search_url}")
                return self._parse_results(final_search_url)
            else:
                print(f"[-] هەڵە لە بەرزکردنەوە: {response.status_code}")
                print(f"       وەڵام: {response.text}")
                return []

        except requests.exceptions.Timeout:
            print("[-] داواکارییەکە لەکاتی دیاریکراودا وەڵام نەدرایەوە (Timeout).")
            return []
        except requests.exceptions.RequestException as req_err:
            print(f"[-] کێشەیەک لە تۆڕدا ڕوویدا: {req_err}")
            return []
        except Exception as e:
            print(f"[-] کێشەیەکی نەزانراو ڕوویدا: {e}")
            return []

    def _parse_results(self, url):
        res = requests.get(url, headers=self.headers, timeout=15)
        if res.status_code != 200:
            print(f"[-] هەڵە لە وەرگرتنی لاپەڕەی ئەنجامەکان: {res.status_code}")
            return []

        soup = BeautifulSoup(res.text, 'html.parser')
        
        found_links = []
        # گەڕان بەدوای هەموو لینکەکاندا
        # یاندێکس زۆرکات لینکەکان لە شێوەی <a class="Link" href="..."> دادەنێت
        for a in soup.find_all('a', href=True):
            link = a['href']
            # یاندێکس زۆرکات لینکە ڕاستەقینەکان دەخاتە ناو پارامیتەرەکانی URLـەوە
            # وەک: https://yandex.com/images/search?rpt=imageview&cbir_id=...&img_url=https%3A%2F%2F...
            # یان: https://yandex.com/search/?text=...&url=https%3A%2F%2F...
            
            # هەوڵدەدەین لینکی ڕاستەقینە لەناو پارامیتەرەکان دەربهێنین
            if "img_url=" in link:
                match_img_url = re.search(r'img_url=(.*?)(?:&|$)', link)
                if match_img_url:
                    link = requests.utils.unquote(match_img_url.group(1))
            elif "url=" in link:
                match_url = re.search(r'url=(.*?)(?:&|$)', link)
                if match_url:
                    link = requests.utils.unquote(match_url.group(1))

            # پشکنینی پلاتفۆرمە کۆمەڵایەتییەکان
            for platform in self.platforms:
                if platform in link:
                    # پاڵاوتنی لینکەکان بۆ ئەوەی تەنها لینکی ئەسڵی بن
                    # ئەم regexـە دەبێت زیاتر بە وریاییەوە بنووسرێت
                    match = re.search(r'(https?://(?:www\.)?' + re.escape(platform) + r'/[^&"\'>\s]+)', link)
                    if match:
                        found_links.append(match.group(1))
        
        return list(set(found_links))

# ئینستەنسێکی AccountFinder دروست دەکەین
finder = ImageAccountFinder()

@app.route('/api/search_image_upload', methods=['POST'])
def search_image_upload():
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    
    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if image_file:
        # دروستکردنی ناوی یونیک بۆ فایلەکە بۆ پاراستنی نێوان داواکارییەکان
        filename = str(uuid.uuid4()) + os.path.splitext(image_file.filename)[1]
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        image_file.save(file_path)
        print(f"[+] وێنە بەرزکرایەوە و پاشەکەوت کرا وەک: {file_path}")

        try:
            results = finder.search_local_image(file_path)
            if results:
                return jsonify({"success": True, "results": results}), 200
            else:
                return jsonify({"success": False, "message": "هیچ ئەکاونتێکی پەیوەندیدار نەدۆزرایەوە."}), 200
        except Exception as e:
            print(f"[-] هەڵە لە جێبەجێکردنی OSINT: {e}")
            return jsonify({"success": False, "message": f"هەڵەیەک ڕوویدا لە کاتی گەڕان: {e}"}), 500
        finally:
            # پاککردنەوەی فایلە کاتییەکە
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[+] فایلی کاتی سڕایەوە: {file_path}")

if __name__ == '__main__':
    # بۆ پەرەپێدانی ناوخۆیی
    # لە بەرهەمهێناندا (production) WSGI server وەک Gunicorn یان uWSGI بەکاربهێنە.
    app.run(debug=True, host='0.0.0.0', port=5000)
