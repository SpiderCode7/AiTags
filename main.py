import datetime

import app
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, BackgroundTasks
from apscheduler.schedulers.blocking import BlockingScheduler

from Ai_Tags import aiTags_isNull,aiTags_change,extract_tags_in_batch,update_ai_tags_to_db
from RapidOCR import rapid_ocr,filter_data

app = FastAPI(title="HxMall AI 打标微服务")

def process_tags_task(pid: int):
    """
    后台执行的具体打标任务（耗时操作）
    """
    try:
        image_map = aiTags_change(pid)

        if not image_map:
            print(f"✅ 商品 {pid} 当前没有需要打标的图片。")
            return

        print("👀 Map数据抽样预览:", image_map)
        imageocr_list = []

        # ⚠️ 修复变量名覆盖：用 item_pid 代替 pid
        for item_pid, urls in image_map.items():
            combined_texts = []
            for url in urls:
                orc = rapid_ocr(url)
                data = filter_data(orc)
                if data:
                    combined_texts.append(data)

            final_product_text = "\n".join(combined_texts)
            imageocr_list.append({
                "id": item_pid,
                "ocr_info": final_product_text
            })

        # 批量调用大模型
        ai_tags_list = extract_tags_in_batch(imageocr_list)
        print("👀 Ai数据返回结果预览:", ai_tags_list)

        # 存入数据库
        update_ai_tags_to_db(ai_tags_list)
        print(f"✨ 商品 {pid} 本轮打标任务圆满完成！")

    except Exception as e:
        # 后台任务报错时，记录日志，不影响主程序
        print(f"❌ 商品 {pid} 任务执行过程中发生异常: {e}")


def run_tagging_job():
    """
    具体的打标任务逻辑，被抽取成一个独立的方法，方便定时器调用
    """
    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 开始执行定时 AI 打标任务...")

    try:
        # 获取空标签的商品图片数据
        image_map = aiTags_isNull()

        if not image_map:
            print("✅ 当前没有需要打标的空标签商品，休息一下。")
            return

        print("👀 Map数据抽样预览:", image_map)
        imageocr_list = []

        # 遍历处理每张图片
        for pid, urls in image_map.items():
            combined_texts = []
            for url in urls:
                orc = rapid_ocr(url)
                data = filter_data(orc)

                if data:
                    combined_texts.append(data)

            final_product_text = "\n".join(combined_texts)

            imageocr_list.append({
                "id": pid,
                "ocr_info": final_product_text
            })

        # 批量调用大模型
        ai_tags_list = extract_tags_in_batch(imageocr_list)
        print("👀 Ai数据返回结果预览:", ai_tags_list)

        update_ai_tags_to_db(ai_tags_list)

        print("✨ 本轮打标任务圆满完成！")

    except Exception as e:
        print(f"❌ 本轮任务执行过程中发生异常: {e}")

@app.post("/api/ai/update_AiTags")
async def trigger_tag_update(pid: int, background_tasks: BackgroundTasks):
    """
    触发单个商品 AI 标签更新的接口
    """
    # 1. 参数校验等前置操作（可选）
    if pid <= 0:
        return {"code": 400, "message": "非法的商品 ID"}

    # 2. ⚡️ 将耗时的任务丢入后台线程池！
    # 就像你往 MQ (RabbitMQ/Kafka) 里发了一条消息一样
    background_tasks.add_task(process_tags_task, pid)

    # 3. 毫秒级立刻响应调用方
    return {
        "code": 200,
        "message": f"商品 {pid} 的图片变更已收到，AI 正在后台静默刷新标签..."
    }


@app.on_event("startup")
def start_scheduler():
    # 改用 BackgroundScheduler，它会在后台线程静默运行，绝对不会阻塞主线程！
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_tagging_job, 'interval', hours=2)
    scheduler.start()

    print("⏰ 定时任务已随 Web 服务成功启动！每 2 小时自动执行一次全局巡检...")

    # 启动时先立刻执行一次全局打标，以免干等
    run_tagging_job()

if __name__ == '__main__':
    # 🚀 真正启动 Web 服务器的地方！
    print("🚀 正在启动 HxMall AI 标签微服务...")
    # uvicorn 会接管整个程序，同时提供 API 接口，并维持后台定时任务运转
    uvicorn.run(app, host="0.0.0.0", port=8000)
