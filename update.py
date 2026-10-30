import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import datetime
import difflib
import html as htmllib
import json
import re
import os
import time

def clean_url(url):
    # RSS 추적 꼬리표(?fromRss=true&trackingCode=rss)를 떼어 글 원래 주소만 남긴다
    return url.split('?')[0].strip()

def make_summary(text, title=''):
    # 글 앞부분에서 인사말·제목 반복을 빼고 150자 안쪽 요약 한두 문장을 만든다
    t = re.sub(r'<[^>]+>', ' ', text or '')
    t = re.sub(r'\s+', ' ', htmllib.unescape(t)).strip()
    # 문장 단위로 나눠 인사말·자기소개 문장과 제목을 되풀이한 첫 문장은 뺀다
    sents = re.split(r'(?<=[.!?])\s+', t)
    kept = []
    for i, s in enumerate(sents):
        if '안녕하세요' in s or '나무결상점입니다' in s:
            continue
        if i == 0 and title and difflib.SequenceMatcher(None, s, title).ratio() > 0.6:
            continue
        kept.append(s)
    t = ' '.join(kept)
    if len(t) <= 150:
        return t
    cut = t[:150]
    m = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
    return cut[:m + 1] if m >= 60 else cut.rstrip() + '…'

def is_gone(post_id):
    # 모바일·PostView 두 주소가 모두 404일 때만 사라진 글로 본다(일시 오류로 지우지 않기 위해)
    for u in ('https://m.blog.naver.com/byunbe/' + post_id,
              'https://blog.naver.com/PostView.naver?blogId=byunbe&logNo=' + post_id):
        try:
            urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=20)
            return False
        except urllib.error.HTTPError as e:
            if e.code != 404:
                return False
        except Exception:
            return False
        time.sleep(0.2)
    return True

summaries = {}
if os.path.exists('summaries.json'):
    with open('summaries.json', 'r', encoding='utf-8') as f:
        summaries = json.load(f)

existing_posts = []
if os.path.exists('index.html'):
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    links = re.findall(r'href="(https://blog\.naver\.com/byunbe/[^"]+)"', content)
    titles = re.findall(r'href="https://blog\.naver\.com/byunbe/[^"]+">([^<]+)</a>', content)
    existing_posts = [(htmllib.unescape(t), clean_url(l)) for t, l in zip(titles, links)]

rss_url = 'https://rss.blog.naver.com/byunbe'
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
        new_posts.append((title.strip(), clean_url(link)))
        # RSS 본문 앞부분 = 요약, 카테고리도 함께 저장(RSS는 최근 50개만 주므로 summaries.json에 쌓아 둔다)
        pid = clean_url(link).rstrip('/').split('/')[-1]
        summ = make_summary(item.find('description').text, title.strip())
        cat = (item.find('category').text or '').strip() if item.find('category') is not None else ''
        entry = summaries.get(pid, {})
        if summ:
            entry['summary'] = summ
        if cat:
            entry['category'] = cat
        summaries[pid] = entry

# 꼬리표를 떼면 같은 글이 두 번 들어 있을 수 있어 중복을 한 번 걸러 낸다(앞쪽 = 최신 유지)
seen = set()
deduped = []
for t, l in existing_posts:
    if l not in seen:
        seen.add(l)
        deduped.append((t, l))
existing_posts = deduped
existing_urls = [p[1] for p in existing_posts]
added = 0
for title, link in new_posts:
    if link not in existing_urls:
        existing_posts.insert(0, (title, link))
        existing_urls.insert(0, link)
        added += 1

# 사라진 글(404) 링크 정리 — 이번 RSS에 없는 오래된 글만 확인한다
rss_ids = {clean_url(l).rstrip('/').split('/')[-1] for _, l in new_posts}
kept = []
removed = 0
for title, link in existing_posts:
    pid = link.rstrip('/').split('/')[-1]
    if pid not in rss_ids and is_gone(pid):
        removed += 1
        continue
    kept.append((title, link))
existing_posts = kept

def render_item(title, link):
    pid = link.rstrip('/').split('/')[-1]
    info = summaries.get(pid, {})
    out = '    <li><a href="' + link + '">' + htmllib.escape(title, quote=False) + '</a>'
    if info.get('category'):
        out += '<span class="cat">' + htmllib.escape(info['category'], quote=False) + '</span>'
    if info.get('summary'):
        out += '<p class="sum">' + htmllib.escape(info['summary'], quote=False) + '</p>'
    return out + '</li>'

list_items = '\n'.join([render_item(title, link) for title, link in existing_posts])

updated = datetime.datetime.now().strftime('%Y년 %m월 %d일')
total = len(existing_posts)

html = (
    '<!DOCTYPE html>\n'
    '<html lang="ko">\n'
    '<head>\n'
    '  <meta charset="UTF-8">\n'
    '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    '  <title>나무결상점 - 건축자재 인테리어 정보</title>\n'
    '  <meta name="description" content="건축과 인테리어, 궁금할 땐 여기!">\n'
    '  <link rel="canonical" href="https://byunbe4421-tech.github.io/">\n'
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
    '    .intro { background: white; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; line-height: 1.7; font-size: 14px; color: #444; }\n'
    '    .cat { display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 10px; background: #e6f0f3; color: #2c5f6e; font-size: 11px; }\n'
    '    .sum { margin: 8px 0 0; color: #666; font-size: 13px; line-height: 1.6; }\n'
    '    footer { text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 13px; }\n'
    '  </style>\n'
    '</head>\n'
    '<body>\n'
    '  <header>\n'
    '    <h1>🌿 나무결상점</h1>\n'
    '    <p>건축과 인테리어, 궁금할 땐 여기! 내외장재부터 인테리어 자재까지</p>\n'
    '    <p><a href="https://blog.naver.com/byunbe" style="color:#4a90a4;">📝 네이버 블로그 바로가기</a></p>\n'
    '  </header>\n'
    '  <p class="updated">마지막 업데이트: ' + updated + ' | 총 ' + str(total) + '개 글</p>\n'
    '  <div class="intro">나무결상점 블로그의 글을 한곳에 모았습니다. 오일스테인·바니쉬·스테인 같은 목재 마감재 고르는 법과 바르는 순서, 방부목·데크 관리 방법을 쉽게 풀어 쓴 글들입니다. 각 글의 앞부분 요약을 함께 적었으니, 궁금한 주제를 골라 네이버 블로그에서 전체 내용을 읽어 보세요.</div>\n'
    '  <ul class="post-list">\n'
    + list_items + '\n'
    '  </ul>\n'
    '  <footer>\n'
    '    <p>© 나무결상점 | 건축자재 인테리어 전문 정보</p>\n'
    '    <p><a href="https://blog.naver.com/byunbe" style="color:#4a90a4;">네이버 블로그</a></p>\n'
    '  </footer>\n'
    '</body>\n'
    '</html>'
)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

# sitemap.xml(우리 사이트 주소만 인정됨)과 robots.txt — 구글이 사이트맵 위치를 알도록
today = datetime.date.today().isoformat()
with open('sitemap.xml', 'w', encoding='utf-8') as f:
    f.write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url>\n'
        '    <loc>https://byunbe4421-tech.github.io/</loc>\n'
        '    <lastmod>' + today + '</lastmod>\n'
        '    <changefreq>daily</changefreq>\n'
        '    <priority>1.0</priority>\n'
        '  </url>\n'
        '  <url>\n'
        '    <loc>https://byunbe4421-tech.github.io/matjiyeo/</loc>\n'
        '    <lastmod>' + today + '</lastmod>\n'
        '    <changefreq>daily</changefreq>\n'
        '    <priority>0.9</priority>\n'
        '  </url>\n'
        '</urlset>\n'
    )
with open('robots.txt', 'w', encoding='utf-8') as f:
    f.write('User-agent: *\nAllow: /\n\nSitemap: https://byunbe4421-tech.github.io/sitemap.xml\n')

with open('summaries.json', 'w', encoding='utf-8') as f:
    json.dump(summaries, f, ensure_ascii=False, indent=1)

print('사라진 글 링크 ' + str(removed) + '개 정리')
print('완료! 새 글 ' + str(added) + '개 추가, 전체 ' + str(total) + '개')
