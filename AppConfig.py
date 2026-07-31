import os
import yaml
import nacos
import pymysql
import multiprocessing
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy import create_engine


# ==========================================
# ⚙️ 模拟 Spring Boot 的 application.yml
# ==========================================
class AppConfig:
    def __init__(self):
        # 1. 本地基础环境变量 (相当于 bootstrap.yml)
        self.NACOS_SERVER = os.getenv("NACOS_SERVER", "127.0.0.1:8848")
        self.NAMESPACE = os.getenv("NACOS_NAMESPACE", "public")
        self.DATA_ID = "hxmall-product-dev.yml"
        self.GROUP = "DEFAULT_GROUP"

        # 2. 业务配置占位符 (等待从 Nacos 加载)
        self.db_config = {}
        self.deepseek_config = {"api_key": "", "base_url": ""}
        self.ocr_config = {"app_key": "", "secret": ""}  # 预留给阿里云/百度云 OCR
        self.db_config = {
            "host": "127.0.0.1",
            "port": 3307,
            "user": "root",
            "password": "",
            "database": "hxmall"
        }

        self.llm = None

        self.mysql = None

        # 3. 启动时立刻初始化 Nacos 并拉取配置
        self._init_nacos()

    def _init_nacos(self):
        print("[Config] 📡 正在连接 Nacos 加载全局配置...")
        client = nacos.NacosClient(self.NACOS_SERVER, namespace=self.NAMESPACE)

        # 首次拉取
        content = client.get_config(self.DATA_ID, self.GROUP)
        if content:
            self._parse_config(content)

        is_web_service = os.getenv("IS_WEB_SERVICE", "False") == "True"

        # 添加热更新监听 (如果是常驻服务的话)
        if is_web_service and multiprocessing.current_process().name == 'MainProcess':
            # 只有主进程才去开启底层的多进程监听器
            client.add_config_watcher(self.DATA_ID, self.GROUP, self._on_config_change)
            print("[Config] 👁️ Nacos 热更新监听器启动成功！")
        else:
            print("[Config] 🛑 当前为离线跑批脚本，跳过 Nacos 热更新监听，防止退出时报错。")

    def _on_config_change(self, args):
        self._parse_config(args)

    def _parse_config(self, content):
        try:
            parsed = yaml.safe_load(content) if isinstance(content, str) else content

            # 加载 MySQL 配置
            pymysql_cfg = parsed.get("pymysql", {})
            if pymysql_cfg:
                self.db_config["host"] = pymysql_cfg.get("host", self.db_config["host"])
                self.db_config["port"] = pymysql_cfg.get("port", self.db_config["port"])

                # 映射：YAML 里的 username -> PyMySQL 需要的 user
                self.db_config["user"] = pymysql_cfg.get("username", self.db_config["user"])
                self.db_config["password"] = pymysql_cfg.get("password", self.db_config["password"])

                # 映射兼防呆：兼容 YAML 里正确的 database 和 你刚手误打成的 datebase
                self.db_config["database"] = pymysql_cfg.get("database",
                                pymysql_cfg.get("datebase", self.db_config["database"]))

            # 加载大模型配置
            ds_cfg = parsed.get("deepseek", {})
            if ds_cfg:
                self.deepseek_config["api_key"] = ds_cfg.get("api-key", "")
                self.deepseek_config["base_url"] = ds_cfg.get("base-url", "https://api.deepseek.com/v1")
                if self.deepseek_config["api_key"]:
                    self.llm = ChatOpenAI(
                        model="deepseek-chat",
                        api_key=self.deepseek_config["api_key"],
                        base_url=self.deepseek_config["base_url"],
                        temperature=0.1
                    )
                    print("[Config] 🤖 LangChain (DeepSeek) 客户端已就绪/已刷新！")

                    # 加载数据库配置
                    try:
                        # 1. 提取动态解析到的配置
                        db_user = self.db_config["user"]
                        db_pwd = self.db_config["password"]
                        db_host = self.db_config["host"]
                        db_port = self.db_config["port"]
                        db_name = self.db_config["database"]

                        # 2. 动态拼接 URL
                        # 对标你 Spring Boot 里的 useUnicode=true&characterEncoding=utf8
                        # Python 这里强烈建议加上 ?charset=utf8mb4，防止生僻字和 Emoji 存入时乱码报错
                        db_url = f"mysql+pymysql://{db_user}:{db_pwd}@{db_host}:{db_port}/{db_name}?charset=utf8mb4"

                        # 3. 创建引擎
                        # 补充 pool_recycle=3600 和 pool_pre_ping=True，防止常驻进程的 MySQL 连接在 8 小时后被服务器自动掐断（经典的 2006 MySQL server has gone away 错误）
                        self.mysql = create_engine(db_url, pool_recycle=3600, pool_pre_ping=True)

                        print(f"[Config] ✅ 数据库加载成功: {db_host}:{db_port}/{db_name}")
                    except Exception as e:
                        print(f"[Config] ❌ 数据库配置失败: {e}")

            # # 加载 OCR 配置
            # ocr_cfg = parsed.get("ocr", {})
            # if ocr_cfg:
            #     self.ocr_config["app_key"] = ocr_cfg.get("app-key", "")
            #     self.ocr_config["secret"] = ocr_cfg.get("secret", "")

            print("[Config] ✅ 核心配置加载/更新成功！")
        except Exception as e:
            print(f"[Config] ❌ 解析 Nacos 配置失败: {e}")


# 🚀 实例化一个单例对象（相当于 Spring 里的 @Bean），其他文件直接 import 它
global_config = AppConfig()