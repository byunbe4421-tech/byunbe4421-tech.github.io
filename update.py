import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import datetime
import difflib
import hashlib
import html as htmllib
import json
import re
import os
import time

SITE = 'https://byunbe4421-tech.github.io'
BLOG_HOME = 'https://blog.naver.com/byunbe'
LATEST_COUNT = 10
UPDATED_MARK = '{{UPDATED}}'


def clean_url(url):
    # RSS 추적 꼬리표(?fromRss=true&trackingCode=rss)를 떼고, 글 주소를 모바일 형식으로 통일한다.
    # PC 주소(blog.naver.com)는 구글 스마트폰 봇에게 본문 없이 리다이렉트만 주고,
    # 모바일 주소(m.blog.naver.com)는 본문 전체를 주기 때문이다(2026-11-03 실측).
    u = url.split('?')[0].strip()
    return re.sub(r'^https://(?:m\.)?blog\.naver\.com/', 'https://m.blog.naver.com/', u)


def post_url(post_id):
    return 'https://m.blog.naver.com/byunbe/' + post_id


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
    for u in (post_url(post_id),
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


def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


summaries = load_json('summaries.json', {})
assign = load_json('assign.json', {})
state = load_json('state.json', {})
cats = load_json('content/categories.json', [])
cat_slugs = [c['slug'] for c in cats]

# ---- 글 목록 불러오기: posts.json이 없으면 예전 index.html(글 링크 목록)에서 한 번 만든다 ----
posts = load_json('posts.json', None)
if posts is None:
    posts = []
    if os.path.exists('index.html'):
        with open('index.html', 'r', encoding='utf-8') as f:
            old = f.read()
        links = re.findall(r'href="(https://(?:m\.)?blog\.naver\.com/byunbe/[^"]+)"', old)
        titles = re.findall(r'href="https://(?:m\.)?blog\.naver\.com/byunbe/[^"]+">([^<]+)</a>', old)
        for t, l in zip(titles, links):
            pid = clean_url(l).rstrip('/').split('/')[-1]
            if pid.isdigit():
                posts.append({'id': pid, 'title': htmllib.unescape(t)})

# ---- RSS에서 새 글 확인 ----
req = urllib.request.Request('https://rss.blog.naver.com/byunbe', headers={'User-Agent': 'Mozilla/5.0'})
root = ET.fromstring(urllib.request.urlopen(req).read())
items = root.find('channel').findall('item')

known = {p['id'] for p in posts}
rss_ids = set()
added = 0
for item in items:
    title = (item.find('title').text or '').strip()
    link = item.find('link').text or ''
    if not link:
        link = item.find('guid').text or ''
    if not (title and link):
        continue
    pid = clean_url(link).rstrip('/').split('/')[-1]
    rss_ids.add(pid)
    # RSS 본문 앞부분 = 요약, 카테고리도 함께 저장(RSS는 최근 50개만 주므로 summaries.json에 쌓아 둔다)
    summ = make_summary(item.find('description').text, title)
    cat = (item.find('category').text or '').strip() if item.find('category') is not None else ''
    entry = summaries.get(pid, {})
    if summ:
        entry['summary'] = summ
    if cat:
        entry['category'] = cat
    summaries[pid] = entry
    if pid not in known:
        posts.append({'id': pid, 'title': title})
        known.add(pid)
        added += 1

# ---- 사라진 글(404) 정리 — 이번 RSS에 없는 오래된 글만 확인한다 ----
kept = []
removed = 0
for p in posts:
    if p['id'] not in rss_ids and is_gone(p['id']):
        removed += 1
        continue
    kept.append(p)
posts = kept
posts.sort(key=lambda p: int(p['id']), reverse=True)

# ---- 새 글을 주제별 페이지에 배정: 제목 키워드로 찾고, 못 찾으면 첫 페이지에 둔다 ----
unassigned = []
for p in posts:
    if p['id'] in assign and assign[p['id']] in cat_slugs:
        continue
    for c in cats:
        if any(k.lower() in p['title'].lower() for k in c['keywords']):
            assign[p['id']] = c['slug']
            break
    else:
        assign[p['id']] = cat_slugs[0]
        unassigned.append(p)


# ---- 페이지 조립 ----
def esc(s):
    return htmllib.escape(s, quote=False)


CSS = (
    '    body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f9f9f9; color: #333; line-height: 1.7; }\n'
    '    header { text-align: center; padding: 32px 0 16px; border-bottom: 2px solid #4a90a4; margin-bottom: 20px; }\n'
    '    header h1 { font-size: 26px; color: #2c5f6e; margin: 0 0 8px; }\n'
    '    header p { color: #666; font-size: 15px; margin: 4px 0; }\n'
    '    nav.top { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: 0 0 24px; padding: 0; }\n'
    '    nav.top a { padding: 4px 12px; border-radius: 14px; background: #e6f0f3; color: #2c5f6e; font-size: 13px; text-decoration: none; }\n'
    '    nav.top a.on { background: #2c5f6e; color: #fff; }\n'
    '    a { color: #2c5f6e; }\n'
    '    .updated { text-align: center; font-size: 12px; color: #999; margin-bottom: 20px; }\n'
    '    .intro { background: white; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; font-size: 14px; color: #444; }\n'
    '    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin: 0 0 28px; padding: 0; list-style: none; }\n'
    '    .cards li { background: white; border-radius: 8px; padding: 14px 18px; border-left: 4px solid #4a90a4; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }\n'
    '    .cards a { font-weight: 600; font-size: 15px; text-decoration: none; }\n'
    '    .cards p { margin: 6px 0 0; font-size: 13px; color: #666; }\n'
    '    article.guide { background: white; border-radius: 8px; padding: 8px 22px 18px; margin-bottom: 28px; font-size: 15px; }\n'
    '    article.guide h2 { font-size: 20px; color: #2c5f6e; margin: 28px 0 8px; padding-bottom: 4px; border-bottom: 1px solid #e3eef1; }\n'
    '    article.guide h3 { font-size: 16px; color: #2c5f6e; margin: 20px 0 6px; }\n'
    '    article.guide table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; display: block; overflow-x: auto; }\n'
    '    article.guide th, article.guide td { border: 1px solid #d9e4e8; padding: 6px 9px; text-align: left; vertical-align: top; }\n'
    '    article.guide th { background: #eef5f7; }\n'
    '    section.posts h2 { font-size: 18px; color: #2c5f6e; }\n'
    '    .post-list { list-style: none; padding: 0; margin: 0; }\n'
    '    .post-list li { background: white; border-radius: 8px; margin-bottom: 10px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-left: 4px solid #4a90a4; }\n'
    '    .post-list li a { text-decoration: none; font-size: 15px; font-weight: 500; }\n'
    '    .post-list li a:hover { color: #4a90a4; text-decoration: underline; }\n'
    '    .sum { margin: 6px 0 0; color: #666; font-size: 13px; }\n'
    '    .note { font-size: 12px; color: #888; }\n'
    '    footer { text-align: center; margin-top: 36px; padding-top: 18px; border-top: 1px solid #ddd; color: #999; font-size: 13px; }\n'
)


def nav_html(current):
    parts = ['<a href="/"' + (' class="on"' if current == 'home' else '') + '>홈</a>']
    for c in cats:
        parts.append('<a href="/' + c['slug'] + '/"' + (' class="on"' if current == c['slug'] else '') + '>' + esc(c['name']) + '</a>')
    return '  <nav class="top">' + ''.join(parts) + '</nav>\n'


def render_post(p):
    info = summaries.get(p['id'], {})
    out = '    <li><a href="' + post_url(p['id']) + '">' + esc(p['title']) + '</a>'
    if info.get('summary'):
        out += '<p class="sum">' + esc(info['summary']) + '</p>'
    return out + '</li>'


def page(title, desc, path, current, h1, sub, body, extra_head=''):
    return (
        '<!DOCTYPE html>\n'
        '<html lang="ko">\n'
        '<head>\n'
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '  <title>' + esc(title) + '</title>\n'
        '  <meta name="description" content="' + htmllib.escape(desc) + '">\n'
        '  <link rel="canonical" href="' + SITE + path + '">\n'
        + extra_head +
        '  <style>\n' + CSS + '  </style>\n'
        '</head>\n'
        '<body>\n'
        '  <header>\n'
        '    <h1>' + esc(h1) + '</h1>\n'
        '    <p>' + esc(sub) + '</p>\n'
        '    <p><a href="' + BLOG_HOME + '" style="color:#4a90a4;">📝 네이버 블로그 바로가기</a></p>\n'
        '  </header>\n'
        + nav_html(current) +
        '  <p class="updated">내용 마지막 변경: ' + UPDATED_MARK + '</p>\n'
        + body +
        '  <footer>\n'
        '    <p>© 나무결상점 | 건축자재 인테리어 전문 정보</p>\n'
        '    <p><a href="' + BLOG_HOME + '" style="color:#4a90a4;">네이버 블로그</a></p>\n'
        '  </footer>\n'
        '</body>\n'
        '</html>\n'
    )


pages = {}  # 파일 경로 -> (URL 경로, 내용)

by_cat = {c['slug']: [p for p in posts if assign.get(p['id']) == c['slug']] for c in cats}

# 메인 페이지
card_items = ''.join(
    '    <li><a href="/' + c['slug'] + '/">' + esc(c['name']) + '</a>'
    '<p>' + esc(c['blurb']) + ' · 글 ' + str(len(by_cat[c['slug']])) + '편</p></li>\n'
    for c in cats
)
latest = '\n'.join(render_post(p) for p in posts[:LATEST_COUNT])
home_body = (
    '  <div class="intro">나무결상점 블로그의 글을 주제별로 모았습니다. 오일스테인·바니쉬 같은 목재 마감재, 방부목·합판 같은 자재 규격, 템바보드·루버 같은 벽 마감재, 합성데크와 외장재, 현관문과 창호까지 여섯 갈래로 나눠 두었습니다. 주제를 고르면 그 분야의 선택 기준과 규격, 시공할 때 주의할 점을 정리한 설명을 볼 수 있고, 자세한 내용은 아래에 이어진 블로그 원문에서 읽을 수 있습니다.</div>\n'
    '  <h2 style="font-size:18px;color:#2c5f6e;">주제별 정리</h2>\n'
    '  <ul class="cards">\n' + card_items + '  </ul>\n'
    '  <section class="posts">\n'
    '  <h2>최근 블로그 글</h2>\n'
    '  <ul class="post-list">\n' + latest + '\n  </ul>\n'
    '  </section>\n'
)
pages['index.html'] = ('/', page(
    '나무결상점 - 건축자재 인테리어 정보',
    '오일스테인·바니쉬 마감재, 방부목·합판 규격, 템바보드·루버, 합성데크, 현관문·창호까지 나무결상점 블로그 글을 주제별로 정리했습니다.',
    '/', 'home', '🌿 나무결상점', '건축과 인테리어, 궁금할 땐 여기! 내외장재부터 인테리어 자재까지', home_body))

# 주제별 페이지
for c in cats:
    slug = c['slug']
    guide_path = 'content/' + slug + '.html'
    with open(guide_path, 'r', encoding='utf-8') as f:
        guide = f.read()
    plist = '\n'.join(render_post(p) for p in by_cat[slug])
    body = (
        '  <article class="guide">\n' + guide + '  </article>\n'
        '  <p class="note">위 내용은 나무결상점 블로그 글을 바탕으로 정리했습니다. 제품 사양은 제조사와 시기에 따라 달라질 수 있으니 구매 전에 확인하세요.</p>\n'
        '  <section class="posts">\n'
        '  <h2>이 주제의 블로그 글 (' + str(len(by_cat[slug])) + '편)</h2>\n'
        '  <ul class="post-list">\n' + plist + '\n  </ul>\n'
        '  </section>\n'
    )
    crumbs = json.dumps({
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': '나무결상점', 'item': SITE + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': c['name'], 'item': SITE + '/' + slug + '/'},
        ]}, ensure_ascii=False)
    pages[slug + '/index.html'] = ('/' + slug + '/', page(
        c['title'] + ' - 나무결상점', c['desc'], '/' + slug + '/', slug,
        c['title'], c['name'], body,
        extra_head='  <script type="application/ld+json">' + crumbs + '</script>\n'))

# ---- 파일 쓰기와 변경 날짜 ----
# 날짜 줄을 뺀 내용의 해시가 바뀐 페이지만 변경일(lastmod)을 오늘로 올린다.
# 새 글이 없고 설명 글도 그대로면 파일과 사이트맵 모두 바뀌지 않는다.
today = datetime.date.today().isoformat()
pstate = state.setdefault('pages', {})


def settle(key, content_for_hash):
    h = hashlib.sha256(content_for_hash.encode('utf-8')).hexdigest()
    st = pstate.get(key)
    if not st or st['hash'] != h:
        pstate[key] = {'hash': h, 'lastmod': today}
    return pstate[key]['lastmod']


urls = []
for fpath, (urlpath, content) in pages.items():
    lastmod = settle(fpath, content)
    final = content.replace(UPDATED_MARK, datetime.date.fromisoformat(lastmod).strftime('%Y년 %m월 %d일'))
    d = os.path.dirname(fpath)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(final)
    urls.append((SITE + urlpath, lastmod))

# 같은 저장소의 다른 정리 페이지(matjiyeo)는 파일 내용이 바뀐 날만 갱신한다
if os.path.exists('matjiyeo/index.html'):
    with open('matjiyeo/index.html', 'r', encoding='utf-8') as f:
        urls.append((SITE + '/matjiyeo/', settle('matjiyeo/index.html', f.read())))

with open('sitemap.xml', 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
    for loc, lm in urls:
        f.write('  <url>\n    <loc>' + loc + '</loc>\n    <lastmod>' + lm + '</lastmod>\n  </url>\n')
    f.write('</urlset>\n')
with open('robots.txt', 'w', encoding='utf-8') as f:
    f.write('User-agent: *\nAllow: /\n\nSitemap: ' + SITE + '/sitemap.xml\n')

save_json('posts.json', posts)
save_json('assign.json', assign)
save_json('summaries.json', summaries)
save_json('state.json', state)

print('사라진 글 링크 ' + str(removed) + '개 정리')
if unassigned:
    print('주제를 못 찾아 첫 페이지에 둔 글: ' + ', '.join(p['id'] + ' ' + p['title'] for p in unassigned))
print('완료! 새 글 ' + str(added) + '개 추가, 전체 ' + str(len(posts)) + '개')
