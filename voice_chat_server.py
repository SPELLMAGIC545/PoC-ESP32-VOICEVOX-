# voice_chat_server.py
# 実行する前に、pip install requests を実行してください。
# 使い方: python voice_chat_server.py

import http.server
import socketserver
import json
import requests
import time
from urllib.parse import urlparse, parse_qs

# --- 設定項目 ---
# サーバーPCのIPアドレスとポート
# ESP32からアクセスするため、PCのIPアドレスを正しく設定してください。
# IPアドレスの確認方法: Windowsならコマンドプロンプトで `ipconfig`、Mac/Linuxならターミナルで `ifconfig` や `ip a`
SERVER_HOST = "0.0.0.0"  # 0.0.0.0 を指定すると、どのIPアドレスからのアクセスも受け付けます
SERVER_PORT = 8001

# ollamaの設定
OLLAMA_API_URL = "http://localhost:11434/api/chat" # 会話履歴を考慮する/api/chatエンドポイントを使用

# VOICEVOX Engineの設定
VOICEVOX_API_URL = "http://localhost:50021"
SPEAKER_ID = 1  # 話者のID (詳細はVOICEVOXのAPIドキュメントを参照)

# 出力ファイル設定
# 実行するたびに新しいファイルが作成されるように、タイムスタンプをファイル名に含めます。
OUTPUT_WAV_DIR = "./"

# --- Ollama通信関数 ---
def get_ollama_chat_response(messages: list) -> str:
    """
    ollamaのチャットエンドポイントにリクエストを送信し、テキスト応答を取得する
    """
    # ESP32から送られてくるモデル名とシステムプロンプトを抽出
    model_name = "sarashina2.2-0.5b:latest" # デフォルト値
    for msg in messages:
        if msg.get("role") == "system":
            # システムプロンプトはそのまま使用
            pass
    
    # ESP32のコードではモデル名を指定していないため、ここで固定値を設定
    # もしESP32側からモデル名を指定したい場合は、JSONに含めるように改造が必要です。
    # ここでは、元のESP32コードのOLLAMA_MODELに相当するものを指定します。
    # 実際のモデル名に合わせて変更してください。
    # 例: "sarashina2.2-0.5b:latest"
    target_model = "sarashina2.2-0.5b:latest" 

    print(f"Ollamaに問い合わせ中... (モデル: {target_model})")
    try:
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False
        }
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60) # タイムアウトを設定
        response.raise_for_status()
        
        response_data = response.json()
        content = response_data.get("message", {}).get("content", "")
        print(f"Ollamaからの応答: {content}")
        return content.strip()
        
    except requests.exceptions.RequestException as e:
        print(f"Ollamaへの接続に失敗しました: {e}")
        return None

# --- VOICEVOX通信関数 ---
def generate_voice(text: str, speaker_id: int, output_dir: str):
    """
    VOICEVOX Engineを使用してテキストから音声を生成し、WAVファイルとして保存する
    """
    if not text:
        print("音声化するテキストがありません。")
        return

    print(f"VOICEVOXで音声を生成中... (話者ID: {speaker_id})")
    try:
        # 1. audio_query (音声合成用のクエリを作成)
        query_params = {"text": text, "speaker": speaker_id}
        res_query = requests.post(f"{VOICEVOX_API_URL}/audio_query", params=query_params)
        res_query.raise_for_status()
        audio_query_data = res_query.json()

        # 2. synthesis (音声合成を実行)
        synth_params = {"speaker": speaker_id}
        res_synth = requests.post(
            f"{VOICEVOX_API_URL}/synthesis",
            params=synth_params,
            json=audio_query_data
        )
        res_synth.raise_for_status()
        
        # 3. WAVファイルとして保存 (ファイル名にタイムスタンプを追加)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = f"{output_dir}output_{timestamp}.wav"
        with open(output_path, "wb") as f:
            f.write(res_synth.content)
        print(f"音声ファイルを保存しました: {output_path}")

    except requests.exceptions.RequestException as e:
        print(f"VOICEVOX Engineへの接続に失敗しました: {e}")

# --- HTTPリクエストハンドラ ---
class ChatHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        # /chat パスへのPOSTリクエストのみを処理
        if self.path == '/chat':
            try:
                # リクエストボディの長さを取得
                content_length = int(self.headers['Content-Length'])
                # リクエストボディを読み込み
                post_data = self.rfile.read(content_length)
                # JSONとしてパース
                request_json = json.loads(post_data.decode('utf-8'))
                
                print("\n--- ESP32からリクエスト受信 ---")
                print(json.dumps(request_json, indent=2, ensure_ascii=False))

                # Ollamaから応答を取得
                messages = request_json.get("messages", [])
                if not messages:
                    raise ValueError("messagesが空です")
                
                ai_response_text = get_ollama_chat_response(messages)

                if ai_response_text:
                    # 音声ファイルを生成 (非同期ではないので、処理が終わるまで待機)
                    generate_voice(ai_response_text, SPEAKER_ID, OUTPUT_WAV_DIR)
                    
                    # ESP32に返すレスポンスを作成
                    response_payload = {
                        "message": {
                            "content": ai_response_text
                        }
                    }
                else:
                    # Ollamaからの応答がなかった場合
                    response_payload = {
                        "message": {
                            "content": "AIからの応答がありませんでした。"
                        }
                    }

                # 成功レスポンスを返す
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(response_payload).encode('utf-8'))

            except Exception as e:
                print(f"エラーが発生しました: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.end_headers()
                error_response = {"error": str(e)}
                self.wfile.write(json.dumps(error_response).encode('utf-8'))
        else:
            # 対応していないパスへのリクエスト
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

# --- メイン処理 ---
if __name__ == "__main__":
    with socketserver.TCPServer((SERVER_HOST, SERVER_PORT), ChatHandler) as httpd:
        print(f"サーバーを開始しました: http://{SERVER_HOST}:{SERVER_PORT}")
        print("ESP32からのチャットリクエストを待機中...")
        httpd.serve_forever()

