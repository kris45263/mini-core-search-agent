"""复现目标不匹配：固定 basic 配置，对照正常页、两个缺失路径及本机 HTTP。"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import httpx

from seekra.cli import read_config
from seekra.retrieval import read_page

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'evals/runs/extract-match-20260910.json'


def main():
    if TARGET.exists():
        raise SystemExit('记录已存在，拒绝覆盖')
    config = read_config(ROOT / '.env')
    base = 'https://api-docs.deepseek.com'
    urls = [base + '/zh-cn/guides/vision', base + '/mini-core-nonexistent-20260908',
            base + '/seekra-nonexistent-20260910', base + '/']
    record = {'date': datetime.now(timezone.utc).isoformat(), 'records': [],
              'scope': '本机 HTTP 与 provider 访问条件不同；不据差异直接推断 provider 根因。'}

    def save():
        text = json.dumps(record, ensure_ascii=False, indent=2)
        for key in ('DEEPSEEK_API_KEY', 'TAVILY_API_KEY'):
            text = text.replace(json.dumps(config[key], ensure_ascii=False)[1:-1], '[已隐藏密钥]')
        TARGET.write_text(text + '\n', encoding='utf-8')

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with TARGET.open('x', encoding='utf-8') as out:
        out.write('{}\n')
    with httpx.Client(timeout=30, follow_redirects=True) as direct:
        for url in urls:
            item = {'url': url, 'route': 'direct_http'}
            try:
                response = direct.get(url)
                title = re.search(r'<title[^>]*>(.*?)</title>', response.text, re.S | re.I)
                item.update(status=response.status_code, final_url=str(response.url),
                    redirects=[{'status': r.status_code, 'url': str(r.url),
                                'location': r.headers.get('location')} for r in response.history],
                    title=title.group(1) if title else None, characters=len(response.text),
                    body_sha256=hashlib.sha256(response.content).hexdigest(),
                    has_first_api_call='Your First API Call' in response.text,
                    has_not_found=bool(re.search('Page Not Found|404 Not Found', response.text, re.I)))
            except httpx.HTTPError as exc:
                item['error'] = type(exc).__name__
            record['records'].append(item)
            save()
            print('direct', url, item.get('status', item.get('error')), flush=True)
    for index, url in enumerate(urls + urls[1:3]):
        item = {'url': url, 'route': 'tavily_then_harness', 'index': index}

        def capture(response):
            response.read()
            item['http_status'] = response.status_code
            if response.status_code == 200:
                item['provider_response'] = response.json()

        with httpx.Client(event_hooks={'response': [capture]}) as client:
            result = read_page(url, client=client, api_key=config['TAVILY_API_KEY'], pages={})
        item['harness_result'] = result
        item['content_sha256'] = hashlib.sha256(result.get('content', '').encode()).hexdigest()
        record['records'].append(item)
        save()
        print('extract', index, result['status'], len(result.get('content', '')), flush=True)


if __name__ == '__main__':
    main()
