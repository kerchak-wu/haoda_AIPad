# -*- coding: utf-8 -*-
"""
pinyin_engine - 好搭AI派 离线拼音输入核心引擎（无 UI 依赖）
功能：
  - 离线全拼输入：音节切分 + 词组优先/字频兜底候选
  - 首字母简拼（输入串中音节可退化为单字母，仅限非首音节）
  - 模糊音可配置（zh/z、ch/c、sh/s、n/l、an/ang、en/eng）
  - 用户词频自学习（data/pinyin_user_freq.json）
  - 外部文本直接上屏（voice_input / phone_bridge 用）
被调用示例：
  from pinyin_engine import PinyinIME
  ime = PinyinIME()
  ime.push_keys('nihao')
  ime.candidates()          # ['你好', ...]
  ime.choose(0)             # 选中候选，ime.committed_text 累积上屏
  ime.commit_external('语音识别结果')   # 语音/手机页文本直接进编辑区
运行环境：Python 3.8+，纯标准库
"""

import bisect
import json
import os

_DEFAULT_DICT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'data', 'pinyin_dict.json')
_DEFAULT_USER_FREQ = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'data', 'pinyin_user_freq.json')

# 用户词频加权系数：自学习一次 ≈ 加这么多通用词频
USER_FREQ_WEIGHT = 50000

# 默认模糊音组（键为输入可能出现的音节，值为可互换的音节列表）
DEFAULT_FUZZY_GROUPS = [
    ('zh', 'z'), ('ch', 'c'), ('sh', 's'),
    ('n', 'l'),
    ('an', 'ang'), ('en', 'eng'), ('in', 'ing'),
]

MAX_SEGMENTATIONS = 16   # 单次查询最多尝试的切分方案数
MAX_SCAN_PER_QUERY = 4000  # 单个前缀查询最多扫描的 key 数


# 声母表（zh/ch/sh 在前，最长匹配）
_INITIALS = ('zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
             'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's', 'y', 'w')


def _split_syllable(s):
    """音节 -> (声母, 韵母)，零声母音节声母为空串"""
    for ini in _INITIALS:
        if s.startswith(ini):
            return ini, s[len(ini):]
    return '', s


def _apply_fuzzy(syllables, fuzzy_map):
    """对音节序列应用模糊音变体（声母、韵母分别映射），返回去重后的变体列表"""
    variants_list = []
    for s in syllables:
        ini, final = _split_syllable(s)
        ini_opts = [ini]
        # 声母变体
        if ini:
            extra = fuzzy_map.get(ini)
            if extra:
                for e in extra:
                    if e not in ini_opts:
                        ini_opts.append(e)
        # 韵母变体
        final_opts = [final]
        extra = fuzzy_map.get(final)
        if extra:
            for e in extra:
                if e not in final_opts:
                    final_opts.append(e)
        opts = []
        for i2 in ini_opts:
            for f2 in final_opts:
                cand = i2 + f2
                if cand not in opts:
                    opts.append(cand)
        variants_list.append(opts)
    results = [[]]
    for opts in variants_list:
        results = [r + [o] for r in results for o in opts]
        if len(results) > 64:
            results = results[:64]
    return results


class PinyinIME(object):
    """离线拼音输入引擎。所有方法均可被外部程序直接调用。"""

    def __init__(self, dict_path=None, user_freq_path=None, fuzzy=False):
        self.dict_path = dict_path or _DEFAULT_DICT
        self.user_freq_path = user_freq_path or _DEFAULT_USER_FREQ
        self.fuzzy_enabled = bool(fuzzy)
        self._load_dict()
        self._load_user_freq()
        # 输入状态
        self._keys = ''        # 当前拼音字母串（仅 a-z）
        self._committed = ''   # 已上屏文本
        self._cand_cache_key = None
        self._cand_cache = []
        self._last_cand_keys = None      # 最近一次查询候选时的拼音串
        self._last_cand_list = []        # 最近一次查询返回的候选列表（choose 用它保证所见即所得）

    # ---------- 数据加载 ----------

    def _load_dict(self):
        with open(self.dict_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._index = data['index']            # 'ni hao' -> [[词, 频], ...]
        self._sorted_keys = sorted(self._index.keys())
        self._syllables = set(data['syllables'])
        # 单字母简拼音节集合（非首音节允许简拼）
        self._initial_letters = set(s[0] for s in self._syllables)
        self._build_abbrev_index()

    def _build_abbrev_index(self):
        """构建首字母简拼索引：取全库频次最高的 3 万个多音节词，
        以首字母串（如 'ni hao' -> 'nh'）为键，供简拼查询"""
        flat = []
        for key, entries in self._index.items():
            if ' ' in key:
                for word, freq in entries[:8]:
                    flat.append((freq, key, word))
        flat.sort(reverse=True)
        self._abbrev_index = {}
        for freq, key, word in flat[:30000]:
            ab = ''.join(s[0] for s in key.split(' '))
            lst = self._abbrev_index.get(ab)
            if lst is None:
                lst = []
                self._abbrev_index[ab] = lst
            lst.append([word, freq])
        for ab in self._abbrev_index:
            self._abbrev_index[ab].sort(key=lambda e: -e[1])

    def _load_user_freq(self):
        self._user_freq = {}
        if os.path.exists(self.user_freq_path):
            try:
                with open(self.user_freq_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._user_freq = data
            except Exception:
                self._user_freq = {}

    def save_user_freq(self):
        try:
            d = os.path.dirname(self.user_freq_path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.user_freq_path, 'w', encoding='utf-8') as f:
                json.dump(self._user_freq, f, ensure_ascii=False)
        except Exception:
            pass

    # ---------- 输入控制 ----------

    def push_keys(self, s):
        """追加拼音字母（自动过滤非法字符，仅保留 a-z）"""
        for ch in s.lower():
            if 'a' <= ch <= 'z':
                self._keys += ch
        return self._keys

    def pop_key(self):
        """删除最后一个拼音字母"""
        if self._keys:
            self._keys = self._keys[:-1]
        return self._keys

    def reset_input(self):
        """清空当前拼音串（不动已上屏文本）"""
        self._keys = ''

    def reset_all(self):
        """清空拼音串和已上屏文本"""
        self._keys = ''
        self._committed = ''

    def commit_external(self, text):
        """外部文本直接上屏（语音识别/手机页推送），并纳入自学习"""
        text = (text or '').strip()
        if text:
            self._committed += text
            if 0 < len(text) <= 4:
                self._user_freq[text] = self._user_freq.get(text, 0) + 1
                self.save_user_freq()
        return self._committed

    def choose(self, i):
        """选中第 i 个候选（0 起），加入上屏文本并自学习；返回选中词或 None。
        优先使用最近一次 candidates() 查询的完整列表（含面板翻页后的词），
        拼音串已变化时按默认 10 条重新查询"""
        if self._last_cand_keys == self._keys and self._last_cand_list:
            cands = self._last_cand_list
        else:
            cands = self.candidates()
        if i < 0 or i >= len(cands):
            return None
        word = cands[i]
        self._committed += word
        self._user_freq[word] = self._user_freq.get(word, 0) + 1
        self.save_user_freq()
        self._keys = ''
        self._cand_cache_key = None
        self._cand_cache = []
        return word

    def choose_first(self):
        """选中当前第一个候选（空格键习惯）；无候选时返回 None"""
        return self.choose(0)

    # ---------- 状态读取 ----------

    @property
    def input(self):
        return self._keys

    @property
    def committed_text(self):
        return self._committed

    # ---------- 音节切分 ----------

    def _segment(self, keys):
        """把字母串切分为音节序列候选列表。
        返回元素为 (音节列表, 尾部残缺字母串或'')；最多 MAX_SEGMENTATIONS 个。"""
        n = len(keys)
        results = []
        # dp[i] = [(音节列表, ...) 从 0..i 为完整音节的切分]（每档最多保留 8 条防爆炸）
        DP_KEEP = 8
        dp = [[] for _ in range(n + 1)]
        dp[0].append([])
        for i in range(n + 1):
            if not dp[i]:
                continue
            for j in range(i + 1, n + 1):
                seg = keys[i:j]
                if seg in self._syllables:
                    for pre in dp[i]:
                        if len(dp[j]) < DP_KEEP:
                            dp[j].append(pre + [seg])
            # 单字母简拼（非首音节限定在 _initial_letters，首音节也允许以降低误切）
            if i < n:
                ch = keys[i]
                if ch in self._initial_letters and len(dp[i + 1]) < DP_KEEP:
                    for pre in dp[i]:
                        dp[i + 1].append(pre + [ch])
                        if len(dp[i + 1]) >= DP_KEEP:
                            break
        for segs in dp[n]:
            results.append((segs, ''))
            if len(results) >= MAX_SEGMENTATIONS:
                return results
        # 尾部残缺音节：完整切分前缀 + 剩余字母作为残缺音节
        for i in range(n, 0, -1):
            if dp[i] and len(keys) - i <= 6:
                tail = keys[i:]
                if tail not in self._syllables:
                    for pre in dp[i]:
                        results.append((pre, tail))
                        if len(results) >= MAX_SEGMENTATIONS:
                            return results
        if not results:
            # 整串都无法切分（如 'sho'）：整体按残缺音节做前缀查询
            results.append(([], keys))
        # 去重，减少重复查询
        uniq = []
        seen = set()
        for segs2, tail in results:
            sig = (tuple(segs2), tail)
            if sig not in seen:
                seen.add(sig)
                uniq.append((segs2, tail))
        return uniq

    # ---------- 候选生成 ----------

    def _prefix_range(self, prefix):
        """在有序 key 表中二分出以 prefix 开头的 key 区间"""
        lo = bisect.bisect_left(self._sorted_keys, prefix)
        hi_bound = prefix[:-1] + chr(ord(prefix[-1]) + 1)
        hi = bisect.bisect_left(self._sorted_keys, hi_bound)
        return lo, hi

    def candidates(self, limit=10):
        """返回当前拼音串的候选词列表（最多 limit 个）"""
        if not self._keys:
            return []
        if self._cand_cache_key == (self._keys, limit):
            return self._cand_cache

        fuzzy_map = {}
        if self.fuzzy_enabled:
            for a, b in DEFAULT_FUZZY_GROUPS:
                fuzzy_map.setdefault(a, []).append(b)
                fuzzy_map.setdefault(b, []).append(a)

        scored = {}
        segs = self._segment(self._keys)

        def add_score(word, score):
            old = scored.get(word)
            if old is None or score > old:
                scored[word] = score

        def add_entries(entries, limit_each, factor=1.0):
            for word, freq in entries[:limit_each]:
                score = (freq + self._user_freq.get(word, 0) * USER_FREQ_WEIGHT) * factor
                add_score(word, score)

        for sylls, partial in segs:
            variants = _apply_fuzzy(sylls, fuzzy_map) if fuzzy_map else [list(sylls)]
            for var in variants:
                base = ' '.join(var)
                if partial:
                    query = (base + ' ' + partial) if base else partial
                    # 残缺尾部：按前缀匹配（key 完全等于 query 的视为精确）
                    self._collect_prefix(query, scored, factor=1.0)
                else:
                    # 完整音节：先取完全匹配
                    entries = self._index.get(base)
                    if entries:
                        add_entries(entries, limit * 3, factor=1.0)
                    # 再收集以该音节序列开头的更长词（降权）
                    self._collect_prefix(base + ' ', scored, factor=0.6,
                                         max_words=max(3, limit // 3))
                # 简拼：切分结果全是单字母、无残缺尾巴且至少两个音节时查简拼索引
                if (not partial and len(var) >= 2
                        and all(len(s) == 1 for s in var)):
                    ab = ''.join(var)
                    entries = self._abbrev_index.get(ab)
                    if entries:
                        add_entries(entries, limit * 2, factor=0.5)

        if not scored:
            # 兜底：整体按原始字母串做前缀查询（如 'sho' -> 'shou' 系列）
            self._collect_prefix(self._keys, scored, factor=1.0, max_words=limit * 4)

        ranked = sorted(scored.items(), key=lambda e: -e[1])
        result = [w for w, _s in ranked[:limit]]
        self._cand_cache_key = (self._keys, limit)
        self._cand_cache = result
        self._last_cand_keys = self._keys
        self._last_cand_list = result
        return result

    def _collect_prefix(self, prefix, scored, factor=1.0, max_words=40):
        """收集以 prefix 开头的所有 key 的候选，写入 scored 字典"""
        lo, hi = self._prefix_range(prefix)
        scanned = 0
        words = 0
        for i in range(lo, hi):
            scanned += 1
            if scanned > MAX_SCAN_PER_QUERY or words > max_words:
                break
            key = self._sorted_keys[i]
            entries = self._index.get(key)
            if entries:
                # key 与 prefix 完全一致按原权重，更长词降权
                f = factor if key == prefix else factor * 0.6
                for word, freq in entries[:3]:
                    score = (freq + self._user_freq.get(word, 0) * USER_FREQ_WEIGHT) * f
                    old = scored.get(word)
                    if old is None or score > old:
                        scored[word] = score
                    words += 1


if __name__ == '__main__':
    import sys
    import time

    t0 = time.time()
    ime = PinyinIME()
    print('词典加载耗时 %.2f 秒, key 数 %d' % (time.time() - t0, len(ime._sorted_keys)))

    def demo(keys):
        ime.reset_all()
        ime.push_keys(keys)
        t = time.time()
        c = ime.candidates(10)
        dt = (time.time() - t) * 1000
        print('%-10s (%.1fms) -> %s' % (keys, dt, c))

    for k in ('ni', 'nihao', 'zhongguo', 'shijie', 'xian', 'nh', 'zg', 'shou', 'sho'):
        demo(k)

    # 交互测试模式: python pinyin_engine.py -i
    if len(sys.argv) > 1 and sys.argv[1] == '-i':
        print('输入拼音串回车出候选，直接回车退出')
        while True:
            s = input('py> ').strip().lower()
            if not s:
                break
            if s == 'bs':
                ime.pop_key()
            else:
                ime.push_keys(s)
            c = ime.candidates(10)
            print('  input=%s -> %s' % (ime.input, c))
            if c:
                pick = input('  选择序号(0-%d, 回车跳过): ' % (len(c) - 1)).strip()
                if pick.isdigit() and int(pick) < len(c):
                    ime.choose(int(pick))
                    print('  committed=%r' % ime.committed_text)
