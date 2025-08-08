import sys
import configparser
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from flask import Flask, request, abort
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    StickerMessageContent,
    ImageMessageContent,
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    StickerMessage,
    MessagingApiBlob

)
import os
import tempfile
import glob

#Config Parser
config = configparser.ConfigParser()
config.read('config.ini')

app = Flask(__name__)

channel_access_token = config['Line']['CHANNEL_ACCESS_TOKEN']
channel_secret = config['Line']['CHANNEL_SECRET']
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash-latest", 
    google_api_key=config["Gemini"]["API_KEY"],
    safety_settings={
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    },
    max_output_tokens=8192
)

handler = WebhookHandler(channel_secret)

configuration = Configuration(
    access_token=channel_access_token
)

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # parse webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def message_text(event):
    gemini_result=gemini_ask(event.message.text)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=gemini_result)]
            )
        )

@handler.add(MessageEvent, message=StickerMessageContent)
def handle_sticker_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[StickerMessage(
                    package_id=event.message.package_id,
                    sticker_id=event.message.sticker_id)
                ]
            )
        )

@handler.add(MessageEvent, message=(ImageMessageContent))
def handle_content_message(event):
    static_tmp_path='static'
    ext = 'jpg'

    with ApiClient(configuration) as api_client:
        line_bot_blob_api = MessagingApiBlob(api_client)
        message_content = line_bot_blob_api.get_message_content(message_id=event.message.id)
        with tempfile.NamedTemporaryFile(dir=static_tmp_path, prefix=ext + '-', delete=False) as tf:
            tf.write(message_content)
            tempfile_path = tf.name

        #刪除資料夾內其他 jpg 檔案
    jpg_files = glob.glob(os.path.join(os.getcwd(), 'static', '*.jpg'))
    for file in jpg_files:
        os.remove(file)
        print(f"Deleted: {file}")

    dist_path = tempfile_path + '.' + ext    #產生的temp檔案加上副檔名
    dist_name = os.path.basename(dist_path)   # 最後的jpg 檔名
    os.rename(tempfile_path, dist_path)
    last_name= "/static/" + dist_name
    gemini_result=gemini_ask(dist_name)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(text=gemini_result)
                ]
            )
        )

def gemini_ask(user_input):
    user_messages = []

    if user_input[-4:].lower() == ".jpg":
        user_prompt = """
        圖片若是數學題目請幫我解答並講解, 若是文言文請幫我翻譯成白話文, 若是文字不是繁體中文, 請翻譯成繁體中文,
        如果是沒有文字的圖,請解釋圖片
        """
        user_messages.append({
            "type" : "text",
            "text" : user_prompt + "各個圖片是什麼 ?"
        })

        image_url="./static/"+ user_input 
        user_messages.append({
            "type" : "image_url",
            "image_url" : image_url
        })
    else :
        user_prompt = """
        你是一個很會講故事的喜劇演員,你都是用幽默的對談跟有趣的範例來說故事,請使用這個主題「
        
        """
        user_messages.append({
            "type" : "text",
            "text" : user_input + "」來創作一個有趣故事,250個字以內,請一律用繁體中文回答。"
        })


    human_messages = HumanMessage(
        content = user_messages
    )
    result = llm.invoke([human_messages])
    #print("Q: " + user_input)
    #print("A: " + result.content)
    return result.contentpip



if __name__ == "__main__":
    app.run(host='0.0.0.0',port=10000)