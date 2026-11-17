# -*- coding: utf-8 -*-
"""
voice_input - 好搭AI派 语音输入封装（无 UI 依赖，可被任何程序调用）
功能：录音开始/结束 + 云端语音识别（VoiceAPI），带 401 重登录重试。
依赖：设备上的 voice_api / audio_recorder 官方库；本机导入失败时可用性为 False。
凭据说明：VOICE_USERNAME / VOICE_PASSWORD 禁止写入任何本地同步文档/代码，
  只允许保存在好搭AI派设备本地的程序副本中（本地副本一律留空）。
调用示例：
    from voice_input import VoiceInput
    vi = VoiceInput()
    if vi.is_available():
        vi.start_record()
        ...  # 用户说话
        text = vi.stop_and_recognize()   # 识别结果文本，失败返回 ''
运行环境：Python 3.8+
"""

import os
import sys
import threading

# 设备官方库位置补充（SSH 直接启动时 PYTHONPATH 可能未生效；不存在时无副作用）
_LIB_DIR = '/home/cxdz/jupyter/lib'
if os.path.isdir(_LIB_DIR) and _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

try:
    from voice_api import VoiceAPI
    from audio_recorder import AudioRecorder
    _VOICE_LIBS_OK = True
except Exception:
    _VOICE_LIBS_OK = False

VOICE_API_URL = "http://www.haohaodada.com/project/voiceAI/ApiZNBW.php"

# 凭据读取优先级：构造参数 > 环境变量 > 设备本地的 credentials.py > 本文件常量
# 本文件常量与仓库同步副本一律留空；凭据只保存在设备副本 credentials.py 中
USERNAME = ''
PASSWORD = ''


def _load_credentials():
    """从设备本地 credentials.py 读取凭据（该文件不属于仓库，重新部署不会被覆盖）"""
    try:
        import credentials
        return (getattr(credentials, 'USERNAME', '') or '',
                getattr(credentials, 'PASSWORD', '') or '')
    except Exception:
        return '', ''

RECORDINGS_DIR = 'recordings'
RECORD_FILENAME = 'pinyin_voice_input.wav'


class VoiceInput(object):
    """语音输入封装。所有方法线程安全级别：录音在调用线程内进行。"""

    def __init__(self, username=None, password=None):
        cred_user, cred_pwd = _load_credentials()
        self.username = username or os.environ.get('VOICE_USERNAME') or cred_user or USERNAME
        self.password = password or os.environ.get('VOICE_PASSWORD') or cred_pwd or PASSWORD
        self._api = None
        self._recorder = None
        self._recording = False
        self._lock = threading.Lock()
        if _VOICE_LIBS_OK and self.username and self.password:
            try:
                self._api = VoiceAPI(VOICE_API_URL)
                token = self._api.get_token(self.username, self.password)
                if not token:
                    # 认证失败（用户名/密码错误或网络不可用）
                    self._api = None
            except Exception:
                self._api = None

    def is_available(self):
        """凭据齐备、库可用且认证成功时为 True"""
        return self._api is not None

    # ---------- 录音 ----------

    def start_record(self):
        """开始录音（阻塞时间极短）。失败抛出异常由调用方处理。"""
        with self._lock:
            if self._recording:
                return
            if self._recorder is None:
                self._recorder = AudioRecorder(sample_rate=16000, channels=1)
            self._recorder.start_recording(device=None)
            self._recording = True

    def stop_and_recognize(self):
        """停止录音并识别。返回识别文本（失败返回 ''）。
        建议在子线程中调用，避免阻塞界面。"""
        with self._lock:
            if not self._recording:
                return ''
            self._recording = False
            try:
                audio_data = self._recorder.stop_recording()
            except Exception:
                return ''
        # 注意：audio_data 是 numpy 数组，不能用 not 判断真值
        if audio_data is None or len(audio_data) == 0:
            return ''
        if not os.path.isdir(RECORDINGS_DIR):
            os.makedirs(RECORDINGS_DIR, exist_ok=True)
        path = self._recorder.save_audio(audio_data, filename=RECORD_FILENAME)
        if not path:
            return ''
        return self.recognize_file(path)

    def cancel_record(self):
        """放弃当前录音"""
        with self._lock:
            if self._recording:
                self._recording = False
                try:
                    self._recorder.stop_recording()
                except Exception:
                    pass

    # ---------- 识别 ----------

    def recognize_file(self, audio_path):
        """识别已有音频文件。401/失败时重新登录再试一次。"""
        if self._api is None:
            return ''
        text = None
        try:
            text = self._api.voice_recognition(audio_path)
        except Exception:
            text = None
        if not text:
            # token 过期等情况：重新登录后重试一次
            try:
                token = self._api.get_token(self.username, self.password)
                if token:
                    text = self._api.voice_recognition(audio_path)
            except Exception:
                text = None
        return (text or '').strip()


if __name__ == '__main__':
    vi = VoiceInput()
    print('语音可用: %s' % vi.is_available())
    if not vi.is_available():
        print('提示：请在设备副本中填写 USERNAME/PASSWORD（本地同步副本禁止保存凭据）')
