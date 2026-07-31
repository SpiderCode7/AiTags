import json
import pymysql
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List

from sqlmodel import Field, Session, SQLModel, select

from AppConfig import global_config
from RapidOCR import rapid_ocr,filter_data
from domain.Product import Product
from domain.ProductImage import ProductImage

# 定义实体类
class ProductTag(BaseModel):
    id: int = Field(description="商品的原始ID")
    ai_tags: str = Field(description="提取的硬核卖点标签，最多5个，用逗号分隔，例如：徕卡光学,骁龙8Gen3")

# 定义Dto
class BatchResult(BaseModel):
    results: List[ProductTag] = Field(description="商品标签打标结果列表")

parser = JsonOutputParser(pydantic_object=BatchResult)

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个电商数据清洗专家。请根据要求提取标签。\n\n{format_instructions}"),
    ("human", "这是需要处理的商品数据：\n{products_data}")
])


def extract_tags_in_batch(products_batch: list) -> list:
    """
    通用商品批量打标方法
    """
    try:
        # 🌟 核心修改：将流水线的组装放到方法内部！
        # 这样每次请求来的时候，都会去 global_config 里拿【当下最新】的 llm 实例
        # 完美解决了 Nacos 动态替换 Key 后，大模型无法刷新的陷阱！
        tagging_chain = prompt | global_config.llm | parser

        # 直接调用 invoke 触发整条流水线
        # 你不需要手写正则，不需要判断 ```json，解析器会自动搞定一切！
        parsed_result = tagging_chain.invoke({
            "products_data": json.dumps(products_batch, ensure_ascii=False),
            # 让解析器把 Java DTO 结构翻译成 AI 能听懂的 Prompt 指令
            "format_instructions": parser.get_format_instructions()
        })

        # 返回最终提取好的字典列表 (相当于 List<Map>)
        return parsed_result.get("results", [])

    except Exception as e:
        print(f"❌ LangChain 流水线处理失败: {e}")
        return []

def aiTags_isNull():
    print("🚀 启动自动化清洗打标流水线...")
    with (Session(global_config.mysql) as session):
        statement = select(Product).where(Product.ai_tags == None)
        products = session.exec(statement).all()

        product_ids = [p.id for p in products]

        if not product_ids:
            product_images = []
        else:
            statement = select(ProductImage.product_id,ProductImage.image_url
                               ).where(ProductImage.product_id.in_(product_ids)
                               ).where(ProductImage.image_type==2)
        with Session(global_config.mysql) as session:
            product_images = session.exec(statement).all()

        # 组装字典
        image_map = {}
        for pid, url in product_images:
            if pid not in image_map:
                image_map[pid] = []
            image_map[pid].append(url)

    return image_map

def aiTags_change(pid:int):
    try:
        product_images = []
        with Session(global_config.mysql) as session:
            statement = select(ProductImage.product_id,ProductImage.image_url
                               ).where(ProductImage.product_id == pid
                               ).where(ProductImage.image_type==2)
            product_images = session.exec(statement).all()

        # 组装字典
        image_map = {}
        for id, url in product_images:
            if id not in image_map:
                  image_map[id] = []
            image_map[id].append(url)
        return image_map
    except Exception as e:
        print(f" 更新查询错误: {e} ")
        return {}


def update_ai_tags_to_db(ai_tags_list: list):
    if not ai_tags_list:
        print("⚠️ Map 为空，没有需要更新的数据")
        return

    update_data = []
    for item in ai_tags_list:
        prod_id = item.get("id")
        tags = item.get("ai_tags")

        # 防呆设计：只有 ID 存在且标签不为空时，才放入更新列表
        if prod_id and tags:
            update_data.append({
                "id": prod_id,  # 必须提供主键
                "ai_tags": tags  # 提供要修改的字段
            })

    if update_data:
        try:
            # 开启数据库会话
            with Session(global_config.mysql) as session:
                # 🚀 批量更新
                session.bulk_update_mappings(Product, update_data)
                session.commit()
                print(f"✅ 成功将 {len(update_data)} 个商品的 AI 标签批量写入数据库！")
        except Exception as e:
            print(f"❌ 批量入库失败，事务已自动回滚: {e}")



if __name__ == "__main__":
    # image_file = "https://hxymall.oss-cn-guangzhou.aliyuncs.com/2026/04/d28e1cde-09ed-4e1c-82d7-97d502a3da31.jpg"
    # mock_data = rapid_ocr(image_file)
    # print("🎉 ocr识图:\n"+ mock_data)
    #
    # step2_lines=filter_data(mock_data)
    # print("🧠 过滤的数据如下：\n"+ step2_lines)

    image_map = aiTags_isNull()
    print("👀 Map数据抽样预览:", image_map)
    imageocr_list = []
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
            "ocr_info" : final_product_text
        })

    ai_tags_list = extract_tags_in_batch(imageocr_list)
    print("👀  Ai数据抽样预览:", ai_tags_list)


    # print("👀 Ai打标签数据抽样预览:")


    # print("🧠 正在通过 LangChain 流水线发送请求...")
    # final_tags = extract_tags_in_batch(mock_data)

    # print("🎉 最终结构化结果：")
    # print(json.dumps(final_tags, indent=4, ensure_ascii=False))