# 配置文件加载器

import sys
from pathlib import Path
from typing import Any,Dict
import tomli
from loguru import logger

def load_config(config_name:str = "config.toml")->Dict[str,Any]:
    """
        加载项目根目录下的 TOML 配置文件。

        Args:
            config_name (str): 配置文件名称。

        Returns:
            Dict[str, Any]: 解析后的配置字典。
    """


    root_dit = Path(__file__).resolve().parent.parent
    config_path = root_dit/config_name

    if not config_path.exists():
        logger.error(f"配置文件不存在:{config_path}")
        sys.exit(1)
    try:
        with open(config_path,"rb") as f:
            config = tomli.load(f)
            logger.info(f"配置文件加载成功{config_path}")
            return config
    except Exception as e:
        logger.error(f"配置文件解析失败:{e}")
        sys.exit(1)
