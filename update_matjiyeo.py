import urllib.request
import xml.etree.ElementTree as ET
import datetime
import re
import os

BLOG_ID = 'matjiyeo'
BLOG_NAME = '온라인 마케팅 연구소'
BLOG_DESC = '온라인 마케팅 연구소 네이버 블로그 글 모음'
HTML_PATH = 'matjiyeo/index.html'

existing_posts = []
if os.path.exists(HTML_PATH):
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    links = re.findall(
        r'href="(https://blog\.naver\.com/' + BLOG_ID + r'/[^"]+)"',
        content
    )
    titles = re.findall(
        r'href="https://blog\.naver\.com/' + BLOG_ID + r'/[^"]+">([^<]+)</a>',
        content
    )
    existing_posts = list(zip(titles, links))

rss_url = f'https://rss.blog.naver.com/{BLOG_ID}'
req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
response = urllib.request.urlopen(req)
xml_data = response.read()
root = ET.fromstring(xml_data)
channel = root.find('channel')
items = channel.findall('item')

new_posts = []
for item in items:
    title = item.find('title').text or ''
    link = item.find('link').text or ''
    if not link:
        link = item.find('guid').text or ''
    if title and link:
        new_posts.append((title.strip(), link.strip()))

existing_urls = [p[1] for p in existing_posts]
added = 0
for title, link in new_posts:
    if link not in existing_urls:
        existing_posts.insert(0, (title, link))
        existing_urls.insert(0, link)
        added += 1

list_items = '\n'.join([
    '    <li><a href="' + link + '">' + title + '</a></li>'
    for title, link in existing_posts
])

updated = datetime.datetime.now().strftime('%Y년 %m월 %d일')
total = len(existing_posts)

html = (
    '<!DOCTYPE html>\n'
    '<html lang="ko">\n'
    '<head>\n'
    '  <meta charset="UTF-8">\n'
    '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    '  <title>' + BLOG_NAME + ' - 네이버 블로그 마케팅 정보</title>\n'
    '  <meta name="description" content="' + BLOG_DESC + '">\n'
    '  <style>\n'
    '    body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f9f9f9; color: #333; }\n'
    '    header { text-align: center; padding: 40px 0 20px; border-bottom: 2px solid #4a90a4; margin-bottom: 30px; }\n'
    '    header h1 { font-size: 28px; color: #2c5f6e; margin-bottom: 8px; }\n'
    '    header p { color: #666; font-size: 15px; }\n'
    '    .updated { text-align: center; font-size: 12px; color: #999; margin-bottom: 20px; }\n'
    '    .post-list { list-style: none; padding: 0; margin: 0; }\n'
    '    .post-list li { background: white; border-radius: 8px; margin-bottom: 12px; padding: 16px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-left: 4px solid #4a90a4; }\n'
    '    .post-list li a { text-decoration: none; color: #2c5f6e; font-size: 15px; font-weight: 500; }\n'
    '    .post-list li a:hover { color: #4a90a4; text-decoration: underline; }\n'
    '    footer { text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 13px; }\n'
    '  </style>\n'
    '</head>\n'
    '<body>\n'
    '  <header>\n'
    '    <h1>🌿 ' + BLOG_NAME + '</h1>\n'
    '    <p>' + BLOG_DESC + '</p>\n'
    '    <p><a href="https://blog.naver.com/' + BLOG_ID + '" style="color:#4a90a4;">📝 네이버 블로그 바로가기</a></p>\n'
    '  </header>\n'
    '  <p class="updated">마지막 업데이트: ' + updated + ' | 총 ' + str(total) + '개 글</p>\n'
    '  <ul class="post-list">\n'
    + list_items + '\n'
    '  </ul>\n'
    '  <footer>\n'
    '    <p>© ' + BLOG_NAME + '</p>\n'
    '    <p><a href="https://blog.naver.com/' + BLOG_ID + '" style="color:#4a90a4;">네이버 블로그</a></p>\n'
    '  </footer>\n'
    '</body>\n'
    '</html>'
)

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print('완료! 새 글 ' + str(added) + '개 추가, 전체 ' + str(total) + '개')
