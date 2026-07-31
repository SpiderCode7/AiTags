from rapidocr_onnxruntime import RapidOCR
import pymysql
import json
import re
import requests  # 👈 新增：用于下载网络图片
import cv2  # 👈 终极修复：用于将图片流解码为标准图像矩阵
import numpy as np  # 👈 终极修复：科学计算基础库
from openai import OpenAI
from AppConfig import global_config

ocr_engine = RapidOCR()

def rapid_ocr(image_path):
    print(f"🔍 正在使用本地 CPU 分析图片: {image_path} ...")


    # ==========================================
    # 🌟 核心修改：智能判断本地图片 vs 网络图片
    # ==========================================
    if image_path.startswith("http://") or image_path.startswith("https://"):
        print("🌐 检测到网络图片 URL，正在将其读取到内存中...")

        proxies_config = {"http": None, "https": None}
        max_retries = 3  # 最大重试次数
        img_input = None
        for attempt in range(max_retries):
            try:
                response = requests.get(image_path, timeout=10, proxies=proxies_config)
                response.raise_for_status()

                image_bytes = np.frombuffer(response.content, dtype=np.uint8)
                img_input = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

                if img_input is None:
                    print("❌ 图片解码失败，可能是图片格式损坏")
                    return "未识别到任何文字"

                break  # 🎉 只要成功一次，直接跳出重试循环

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ 图片下载超时或失败，正在进行第 {attempt + 1} 次重试...")
                    import time
                    time.sleep(1)  # 稍微歇1秒再试，防止被服务器拉黑
                else:
                    print(f"❌ 重试 {max_retries} 次后依然失败: {e}")
                    return "未识别到任何文字"
    else:
        # 如果是本地路径，直接沿用原来的字符串
        img_input = image_path

    # 将图片流（或路径）传给 OCR 引擎
    result, elapse = ocr_engine(img_input)

    if result is None:
        return "未识别到任何文字"

    extracted_text = ""
    last_y = 0

    for text_block in result:
        box = text_block[0]
        text_content = text_block[1]

        # 取文字块左上角的 Y 坐标
        current_y = box[0][1]

        # 核心逻辑：进行 Y 坐标高度比对，还原原本的表格与换行排版
        if last_y != 0 and abs(current_y - last_y) > 15:
            extracted_text += "\n"  # 高度差大于 15 像素，判定为换行
        else:
            if last_y != 0:
                extracted_text += "\t"  # 同一行的内容用 Tab 制表符隔开

        extracted_text += text_content
        last_y = current_y

    # 🌟 修复：兼容最新版 RapidOCR，将列表里的三个耗时阶段加起来
    if isinstance(elapse, list):
        total_time = sum(elapse)
        print(f"⏱️ 识别耗时: 总计 {total_time:.3f} 秒")
    else:
        print(f"⏱️ 识别耗时: {elapse:.3f} 秒")

    return extracted_text.strip()

def filter_data(lines):
    lines = lines.split('\n')
    # 制定一本“违禁词词典”
    blacklist = [  # 2. 客服与引导类 (Customer Service & CTA)
        "客服", "下单", "抽奖", "二维码", "扫码", "关注", "旗舰店", "官方正品",
        "加入购物车", "联系我们", "晒单", "好评", "返现", "评价", "粉丝",

        # 3. 售后与免责类 (After-sales & Legal)
        "售后", "质保", "保修", "退换", "包退", "解释权", "仅供参考",
        "实际为准", "数据来源", "实验室测试", "环境不同", "一切以实物为准",

        # 4. 营销排版词 / 极度主观的形容词 (Marketing Fluff)
        "重新定义", "震撼上市", "无与伦比", "突破极限", "宛如", "仿佛",
        "身临其境", "尽享", "随心所欲", "让照片更出彩", "每一拍都是",

        # 5. 常见的 OCR 误识别符号 (Noise)
        "点击", "滑动", "详情页", "首页", "¥", "￥", "RMB"]

    # 🟢 核心天书解析（列表推导式）
    step1_lines = [line for line in lines if not any(word in line for word in blacklist)]

    step2_lines = [line for line in step1_lines if 3 < len(line) < 50]

    step3_lines = []
    for line in step2_lines:
        # 1. 检查这一行是不是用 \t (制表符) 隔开的
        if '\t' in line:
            # 切碎成词语数组：['鲜艳', '明快', '动漫', '胶片', '鲜艳', '明快'...]
            words = line.split('\t')
            # 同样使用 fromkeys 保持顺序去重：['鲜艳', '明快', '动漫', '胶片']
            unique_words = list(dict.fromkeys(words))
            # 再用 \t 强力胶水粘回去
            clean_line = '\t'.join(unique_words)
            step3_lines.append(clean_line)

        else:
            step3_lines.append(line)

        # 全局的“行级去重”
        # 我们再次利用字典键唯一的特性，把完全相同的行折叠成一行，且不打乱原有排版顺序！
    step4_lines = list(dict.fromkeys(step3_lines))
    # print("step4_lines:"+str(step4_lines))

    # 子类去重
    final_lines = []
    for i, line_a in enumerate(step4_lines):
        # 把这一行按 \t 拆成集合 (Set)，比如 {'鲜艳', '明快', '动漫', '胶片'},{'鲜艳', '明快', '动漫', '胶片','柔和'}
        # print(str(i)+":"+line_a)
        set_a = set(line_a.split('\t'))
        # print("序号:"+str(i)+" "+"set_a:"+ str(set_a))
        is_swallowed = False
        for j, line_b in enumerate(step4_lines):
            # print(str(j) + ":" + line_b)
            if i != j:
                # print("触发判断")
                set_b = set(line_b.split('\t'))
                # print("序号:"+str(i)+" "+"set_b:" + str(set_b))
                # 核心逻辑：
                # 如果 A 集合里的所有词，B 集合全都有 (A is subset of B)
                # 并且 B 的词汇量严格大于 A，说明 A 是残缺的冗余数据
                if set_a.issubset(set_b) and len(set_a) < len(set_b):
                    is_swallowed = True
                    break  # 只要被任何一条“大鱼”吃掉，A 就死了，直接跳出循环
        # 如果没有被任何大鱼吞噬，A 就能活下来
        if not is_swallowed:
            final_lines.append(line_a)

    return "\n".join(final_lines)


if __name__ == "__main__":
    # 假设你有一张名为 sample.jpg 的商品参数图放在代码同级目录
    # 你可以随便截一张带有商品参数的图命名为 sample.jpg 来测试
    image_file = "https://hxymall.oss-cn-guangzhou.aliyuncs.com/2026/04/d28e1cde-09ed-4e1c-82d7-97d502a3da31.jpg"

    try:
        text = rapid_ocr(image_file)
        text = """拍尽明暗冷暖
无论是阳光洒下的暖意，还是夜色笼罩的蓝调，
XMAGE色卡
雅仕女图
鲜艳	明快	动漫	胶片	鲜艳	明快	动漫	胶片
鲜艳	明快	动漫	胶片	鲜艳	明快	动漫	胶片	柔和"""

        print("\n✨ 识别结果如下：")
        print("-" * 30)
        print(text)
        print("-" * 30)

        final_text = filter_data(text)
        print("\n✨ 过滤结果如下：")
        print("-" * 30)
        print(final_text)
        print("-" * 30)
    except Exception as e:
        print(f"❌ 运行失败，请检查图片是否存在: {e}")