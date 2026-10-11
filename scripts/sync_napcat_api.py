import sys
import json
import urllib.request

url = 'https://raw.githubusercontent.com/NapNeko/NapCatDocs/main/src/api/4.18.37/openapi.json'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))

lines = []
lines.append('# NapCat QQ API 规范 (v4.18.37)')
lines.append('')
lines.append('> **文档来源**: [NapCatQQ 官方 API (4.18.37)](https://napneko.github.io/api/4.18.37)')
lines.append('> **版本**: 4.18.37 | **端点总数**: %d' % len(data.get('paths', {})))
lines.append('')
lines.append('本文档同步自 NapCatQQ 官方 4.18.37 接口规范，包含所有 HTTP API 接口路径、请求方法、摘要说明与核心数据模型，供 TQSync 项目调用与扩展 QQ 接口时参考。')
lines.append('')

# Group by tag
tags_map = {}
for path, methods in data.get('paths', {}).items():
    for method_name, detail in methods.items():
        tag = (detail.get('tags') or ['其他'])[0]
        if tag not in tags_map:
            tags_map[tag] = []
        tags_map[tag].append({
            'path': path,
            'method': method_name.upper(),
            'summary': detail.get('summary', ''),
            'description': (detail.get('description') or '').strip(),
            'deprecated': detail.get('deprecated', False),
            'requestBody': detail.get('requestBody', {}),
            'responses': detail.get('responses', {})
        })

lines.append('## 目录')
for tag, items in tags_map.items():
    lines.append(f'- [{tag} ({len(items)})](#{tag})')
lines.append('- [数据模型 / Schemas (39)](#数据模型--schemas)')
lines.append('')

for tag, items in tags_map.items():
    lines.append(f'## {tag}')
    lines.append('')
    lines.append('| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |')
    lines.append('| :--- | :--- | :--- | :--- |')
    for item in items:
        p = item['path']
        m = item['method']
        s = item['summary'] or '-'
        d = item['description'].replace('\r', ' ').replace('\n', ' ')
        if len(d) > 80:
            d = d[:77] + '...'
        if not d:
            d = '-'
        lines.append(f'| `{p}` | `{m}` | {s} | {d} |')
    lines.append('')

lines.append('## 数据模型 / Schemas')
lines.append('')
schemas = data.get('components', {}).get('schemas', {})
for s_name, s_val in schemas.items():
    s_title = s_val.get('title') or s_name
    lines.append(f'### `{s_name}`')
    if s_val.get('description'):
        lines.append(f"{s_val['description']}")
        lines.append('')
    props = s_val.get('properties', {})
    if props:
        lines.append('| 字段 | 类型 | 说明 / 描述 |')
        lines.append('| :--- | :--- | :--- |')
        for p_name, p_val in props.items():
            p_type = p_val.get('type', 'any')
            p_desc = p_val.get('description', '') or p_val.get('title', '') or '-'
            p_desc = p_desc.replace('\r', ' ').replace('\n', ' ')
            lines.append(f'| `{p_name}` | `{p_type}` | {p_desc} |')
        lines.append('')
    else:
        lines.append('*无特殊字段定义或为空对象*')
        lines.append('')

with open('d:/TQSync/NapCatQQAPI.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')

print('NapCatQQAPI.md generated successfully!')
