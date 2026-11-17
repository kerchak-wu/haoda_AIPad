# -*- coding: utf-8 -*-
"""
构建拼音词典 - 好搭AI派 拼音输入应用维护工具
功能：合并三个开源数据源，生成 pinyin_engine.py 使用的 data/pinyin_dict.json
  1. fxsjy/jieba dict.txt          -> 简体词频（词 + 频次，MIT 许可）
  2. mozillazg/phrase-pinyin-data  -> 词语拼音（词 -> 带调拼音）
  3. mozillazg/pinyin-data         -> 单字拼音（字 -> 多个带调读音）
数据源下载地址（jsDelivr CDN 镜像，GitHub 直连不通时也可用）：
  https://cdn.jsdelivr.net/gh/fxsjy/jieba@master/jieba/dict.txt
  https://cdn.jsdelivr.net/gh/mozillazg/phrase-pinyin-data@master/pinyin.txt
  https://cdn.jsdelivr.net/gh/mozillazg/pinyin-data@master/pinyin.txt
用法：
  python 构建拼音词典.py                       # 使用默认源路径
  python 构建拼音词典.py <jieba.txt> <phrase.txt> <chars.txt> <输出.json>
运行环境：Python 3.8+，纯标准库
"""

import argparse
import json
import os
import re
import sys
import time

DEFAULT_FREQ = os.path.join(os.environ.get('TEMP', '/tmp'), 'jieba_dict.txt')
DEFAULT_PHRASE = os.path.join(os.environ.get('TEMP', '/tmp'), 'phrase_pinyin.txt')
DEFAULT_CHARS = os.path.join(os.environ.get('TEMP', '/tmp'), 'char_pinyin.txt')
DEFAULT_OUT = os.path.join('data', 'pinyin_dict.json')

# 单字候选/词组条目按 key 收纳上限，防止个别 key 膨胀
MAX_ENTRIES_PER_KEY = 600
MAX_WORD_LEN = 4

# 带调音节 -> 无调音节映射（ü 统一映射为 v，与常见拼音输入法键位一致）
_TONE_MAP = {}
for _base, _pairs in (
    ('a', 'āáǎà'),
    ('e', 'ēéěè'),
    ('i', 'īíǐì'),
    ('o', 'ōóǒò'),
    ('u', 'ūúǔù'),
):
    for _ch in _pairs:
        _TONE_MAP[_ch] = _base
for _ch in 'ǖǘǚǜ':
    _TONE_MAP[_ch] = 'v'
_TONE_MAP['ü'] = 'v'

CJK_RE = re.compile(u'[\u4e00-\u9fff]+$')


def strip_tone(syllable):
    """带调音节 -> 无调音节；含无法映射字符时返回 None"""
    out = []
    for ch in syllable:
        if ch in _TONE_MAP:
            out.append(_TONE_MAP[ch])
        elif ch.isascii() and ch.isalpha():
            out.append(ch.lower())
        else:
            return None
    s = ''.join(out)
    return s if s else None


def load_phrase_pinyin(path):
    """词语拼音：词 -> [无调音节, ...]，同时收集合法音节集合"""
    phrase = {}
    syllables = set()
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                continue
            word, _, py = line.partition(':')
            word = word.strip()
            parts = [strip_tone(p) for p in py.split()]
            if not parts or any(p is None for p in parts):
                continue
            if not CJK_RE.match(word):
                continue
            phrase[word] = parts
            syllables.update(parts)
    return phrase, syllables


def load_char_pinyin(path, syllables):
    """单字拼音：字 -> [无调音节, ...]（只保留合法音节的读音）"""
    chars = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = re.match(r'U\+[0-9A-Fa-f]+:\s*(.+?)\s*#', line)
            if not m:
                continue
            readings = m.group(1).split(',')
            hanzi = ''
            for ch in line:
                if u'\u4e00' <= ch <= u'\u9fff':
                    hanzi = ch
                    break
            if not hanzi:
                continue
            valid = []
            for r in readings:
                s = strip_tone(r)
                if s and s in syllables:
                    valid.append(s)
            if valid:
                chars[hanzi] = valid
    return chars


def load_jieba_freq(path):
    """词频：词 -> 次数（jieba dict.txt，格式：词 频次 词性；保留 1~4 个汉字）"""
    freq = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            pieces = line.split()
            if len(pieces) < 2:
                continue
            word, count = pieces[0], pieces[1]
            if not CJK_RE.match(word):
                continue
            if len(word) > MAX_WORD_LEN:
                continue
            try:
                n = int(count)
            except ValueError:
                continue
            if n < 1:
                continue
            # 同一词保留最大次数
            if word not in freq or n > freq[word]:
                freq[word] = n
    return freq


def build(freq_path, phrase_path, chars_path, out_path):
    t0 = time.time()
    print('1/4 读取词语拼音: %s' % phrase_path)
    phrase, syllables = load_phrase_pinyin(phrase_path)
    print('     词语 %d 条，合法音节 %d 个' % (len(phrase), len(syllables)))

    print('2/4 读取单字拼音: %s' % chars_path)
    chars = load_char_pinyin(chars_path, syllables)
    print('     单字 %d 个' % len(chars))

    print('3/4 读取词频并合并: %s' % freq_path)
    freq = load_jieba_freq(freq_path)
    print('     词频条目 %d 条' % len(freq))

    index = {}
    n_char_entry = 0
    n_phrase_hit = 0
    n_char_compose = 0
    for word, n in freq.items():
        if len(word) == 1:
            readings = chars.get(word)
            if not readings:
                continue
            # 保持原文件读音顺序（首个读音即最常用读法），去重
            ordered = []
            for s in readings:
                if s not in ordered:
                    ordered.append(s)
            for i, s in enumerate(ordered):
                # 次读音降权（多音字的罕用读法），避免污染候选排序
                eff = n if i == 0 else max(1, n // 20)
                index.setdefault(s, []).append([word, eff])
                n_char_entry += 1
            n_char_compose += 1
        else:
            py = phrase.get(word)
            if py is None:
                # 词语拼音缺失时用单字首读兜底拼合
                ok = True
                py = []
                for ch in word:
                    r = chars.get(ch)
                    if not r:
                        ok = False
                        break
                    py.append(r[0])
                if not ok:
                    continue
            else:
                n_phrase_hit += 1
            index.setdefault(' '.join(py), []).append([word, n])

    # 排序 + 同 key 去重 + 截断
    total = 0
    for key in index:
        seen = set()
        uniq = []
        for word, n in sorted(index[key], key=lambda e: -e[1]):
            if word in seen:
                continue
            seen.add(word)
            uniq.append([word, n])
            if len(uniq) >= MAX_ENTRIES_PER_KEY:
                break
        index[key] = uniq
        total += len(uniq)

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    print('4/4 写出词典: %s' % out_path)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'version': 1,
            'source': 'fxsjy/jieba dict.txt + mozillazg/phrase-pinyin-data + mozillazg/pinyin-data',
            'syllables': sorted(syllables),
            'index': index,
        }, f, ensure_ascii=False, separators=(',', ':'))

    size_mb = os.path.getsize(out_path) / 1024.0 / 1024.0
    print('=' * 50)
    print('音节 key 数: %d' % len(index))
    print('候选条目总数: %d' % total)
    print('  词组（词库直配拼音）: %d' % n_phrase_hit)
    print('  词组（单字拼音兜底）: %d' % (len(freq) - n_phrase_hit - n_char_compose))
    print('  单字读音条目: %d' % n_char_entry)
    print('文件大小: %.2f MB' % size_mb)
    print('耗时: %.1f 秒' % (time.time() - t0))


def main():
    parser = argparse.ArgumentParser(description='构建拼音输入词典')
    parser.add_argument('sources', nargs='*', default=None,
                        help='依次为 jieba_dict.txt phrase_pinyin.txt char_pinyin.txt 输出.json')
    args = parser.parse_args()
    if args.sources and len(args.sources) == 4:
        freq, phrase, chars, out = args.sources
    else:
        freq, phrase, chars, out = (DEFAULT_FREQ, DEFAULT_PHRASE,
                                    DEFAULT_CHARS, DEFAULT_OUT)
    for p in (freq, phrase, chars):
        if not os.path.exists(p):
            print('缺少数据源文件: %s' % p)
            print('请先从上方说明中的 CDN 地址下载三个数据文件')
            sys.exit(1)
    build(freq, phrase, chars, out)


if __name__ == '__main__':
    main()
