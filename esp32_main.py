# esp32_main.py (APモード / サーバーPC連携版)

import network
import time
import urequests
import ujson
import socket
import sys

# --- ユーザー設定項目 ---
# [任意] ESP32が公開するアクセスポイントの情報
AP_SSID = "omocha"
AP_PASSWORD = "password1234" # 8文字以上にしてください

# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# サーバーPCで起動した `voice_chat_server.py` のIPアドレスとポートを設定
# 例: サーバーPCのIPが 192.168.4.2 で、ポートが 8000 の場合
SERVER_PC_URL = "http://192.168.4.2:8001/chat"
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

# 使用するモデル名とシステムプロンプト (これらはサーバーPCに送信されます)
OLLAMA_MODEL = "sarashina2.2-0.5b:latest" # サーバー側で実際に使用するモデル名と合わせてください
SYSTEM_PROMPT = "あなたは親切なアシスタントです。簡潔に、分かりやすく日本語で回答してください。"
# -------------------------

class ChatSession:
    """会話の履歴を管理するクラス"""
    def __init__(self, system_prompt="", max_interactions=10):
        self.system_prompt = system_prompt
        self.max_length = max_interactions * 2
        self.history = []
        if self.system_prompt:
            self.history.append({"role": "system", "content": self.system_prompt})
        print(f"新しいチャットセッションを開始しました。最新{max_interactions}回のやり取りを記憶します。")

    def add_user_message(self, text):
        self.history.append({"role": "user", "content": text})

    def add_model_message(self, text):
        self.history.append({"role": "assistant", "content": text})
        # 履歴が最大長を超えた場合、古い会話から削除
        conversation_len = len(self.history) - (1 if self.system_prompt else 0)
        while conversation_len > self.max_length:
            self.history.pop(1) # systemプロンプトの次に古いuserメッセージを削除
            self.history.pop(1) # その次のassistantメッセージを削除
            conversation_len -= 2

    def get_messages(self):
        return self.history

    def clear(self):
        system_msg = self.history[0] if self.system_prompt else None
        self.history = []
        if system_msg:
            self.history.append(system_msg)
        print("会話履歴をリセットしました。")

def setup_ap():
    """ESP32をアクセスポイントモードで起動する"""
    sta_if = network.WLAN(network.STA_IF)
    if sta_if.active():
        sta_if.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, authmode=3, password=AP_PASSWORD) # WPA2-PSK
    while not ap.active():
        time.sleep(1)
    print('--- APモード準備完了 ---')
    print(f'SSID: {ap.config("essid")}, IPアドレス: {ap.ifconfig()[0]}')
    print('スマートフォンやPCからこのWi-Fiに接続してください。')
    return True

def ask_server_pc(chat_session):
    """サーバーPCに会話データを送信し、AIの応答を取得する"""
    headers = {'Content-Type': 'application/json'}
    # サーバーに送信するデータ (モデル名と会話履歴)
    data = {"model": OLLAMA_MODEL, "messages": chat_session.get_messages()}
    
    print(f"\n> サーバーPC ({SERVER_PC_URL}) に問い合わせ中...")
    try:
        # ujson.dumpsでPython辞書をJSON文字列に変換し、UTF-8でエンコード
        request_body = ujson.dumps(data).encode('utf-8')
        response = urequests.post(SERVER_PC_URL, data=request_body, headers=headers)
        
        if response.status_code == 200:
            json_response = response.json()
            # サーバーからのレスポンス形式に合わせてキーを取得
            return json_response.get("message", {}).get("content", "エラー: 'content'キーが見つかりません。")
        else:
            return f"エラー: サーバーからステータスコード {response.status_code} を受信しました。詳細: {response.text}"
    except Exception as e:
        return f"エラー: サーバーPCへの接続に失敗しました: {e}"

def get_html_page():
    """チャット用のHTMLページを返す"""
    # HTML/CSS/JSは変更なし
    html = """<!DOCTYPE html><html><head><title>ESP32 AI Chat</title><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;margin:0;display:flex;flex-direction:column;height:100vh;background-color:#f7f7f7}h1{text-align:center;color:#333;margin:20px}#chatbox{flex-grow:1;overflow-y:auto;padding:20px;border-top:1px solid #ddd;border-bottom:1px solid #ddd}.message{display:flex;max-width:80%;padding:10px 15px;border-radius:18px;margin-bottom:10px;line-height:1.4;word-wrap:break-word}.user{background-color:#007bff;color:white;align-self:flex-end;margin-left:auto}.ai{background-color:#e9e9eb;color:#333;align-self:flex-start;margin-right:auto}#form{display:flex;padding:10px;background-color:#fff}#userInput{flex-grow:1;border:1px solid #ccc;border-radius:20px;padding:10px 15px;font-size:16px}#sendBtn{background-color:#007bff;color:white;border:none;border-radius:50%;width:44px;height:44px;margin-left:10px;font-size:20px;cursor:pointer}#status{text-align:center;padding:5px;font-size:0.8em;color:gray;height:20px}</style></head><body><h1>🤖 ESP32 AI Chat</h1><div id="chatbox"></div><div id="status">メッセージをどうぞ</div><form id="form" onsubmit="sendMessage(event)"><input type="text" id="userInput" placeholder="メッセージを入力..." autocomplete="off"><button id="sendBtn" type="submit">➤</button></form><script>const chatbox=document.getElementById('chatbox'),userInput=document.getElementById('userInput'),sendBtn=document.getElementById('sendBtn'),status=document.getElementById('status');function addMessage(e,t){const n=document.createElement('div');n.className="message "+t,n.innerText=e,chatbox.appendChild(n),chatbox.scrollTop=chatbox.scrollHeight}async function sendMessage(e){e.preventDefault();const t=userInput.value;if(!t.trim())return;addMessage(t,'user'),userInput.value='',status.innerText='AIが考え中...',sendBtn.disabled=!0;try{const e=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t})}),n=await e.json();addMessage(n.response,'ai')}catch(e){addMessage('エラーが発生しました: '+e,'ai')}finally{status.innerText='メッセージをどうぞ',sendBtn.disabled=!1,userInput.focus()}}</script></body></html>"""
    return html

# --- メイン処理 ---
if setup_ap():
    chat = ChatSession(system_prompt=SYSTEM_PROMPT, max_interactions=10)
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    print('Webサーバーがポート80で待機中...')
    
    while True:
        try:
            conn, addr = s.accept()
            print('接続元: %s' % str(addr))
            request_bytes = conn.recv(1024)

            try:
                request_str = request_bytes.decode('utf-8')
            except UnicodeError:
                conn.close()
                continue

            if request_str.find('POST /chat') != -1:
                try:
                    body_start = request_str.find('\r\n\r\n') + 4
                    json_str = request_str[body_start:]
                    
                    data = ujson.loads(json_str)
                    user_input = data['message']
                    
                    print(f"ユーザー (Webから): {user_input}")

                    if user_input.lower() == 'clear':
                        chat.clear()
                        ai_response = "会話の履歴をリセットしました。"
                        print(f"システム: {ai_response}")
                    else:
                        chat.add_user_message(user_input)
                        ai_response = ask_server_pc(chat) # サーバーPCに問い合わせる関数を呼び出す
                        print(f"AI: {ai_response}")
                        if not ai_response.startswith("エラー:"):
                            chat.add_model_message(ai_response)
                    
                    # ブラウザに返すJSON形式を元の形式に合わせる
                    response_data = ujson.dumps({'response': ai_response})
                    conn.send('HTTP/1.1 200 OK\n')
                    conn.send('Content-Type: application/json; charset=utf-8\n')
                    conn.send('Connection: close\n\n')
                    conn.sendall(response_data)
                except Exception as e:
                    print(f"チャットリクエストの処理中にエラー: {e}")
                    conn.send('HTTP/1.1 500 Internal Server Error\nConnection: close\n\n')
            else:
                # GETリクエストなど、/chat以外の場合はHTMLページを返す
                response = get_html_page()
                conn.send('HTTP/1.1 200 OK\n')
                conn.send('Content-Type: text/html; charset=utf-8\n')
                conn.send('Connection: close\n\n')
                conn.sendall(response)
            
            conn.close()
        except OSError as e:
            conn.close()
            print(f"ソケットエラー: {e}")
        except KeyboardInterrupt:
            s.close()
            break
