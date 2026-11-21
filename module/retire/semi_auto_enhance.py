"""半自动强化。

不依赖「船坞满」弹窗，也不做退役：在「工具 → 半自动强化」点「立即运行」，
脚本就按「强化设置」的筛选条件（排序 / 索引 / 阵营 / 稀有度 / 附加索引）
进船坞，从第一艘开始逐个强化，强化不动就向左滑动换下一艘。

跑完一轮就自己把下一次执行时间推到很久以后（等价于关掉这次启动），
所以它不会像别的任务那样到点自动跑，下次要用再点一次「立即运行」。

与退役流程里的强化共用同一套代码（module.retire.enhancement.Enhancement）：
- 筛选条件：General.Enhance.*
- 强化艘数：优先用本任务自己的 Count，0 表示跟随「强化设置 - 强化数量」
"""
from module.config.config import TaskEnd
from module.logger import logger
from module.retire.enhancement import Enhancement
from module.ui.page import page_dock

# 跑完一轮后的「下次执行时间」间隔（分钟），约 10 年，等价于不要自动再跑
NO_AUTO_RUN_MINUTE = 5256000


class SemiAutoEnhance(Enhancement):
    def _enhance_count(self):
        """本任务自己的数量上限，0 表示跟随「强化设置」。"""
        return int(getattr(self.config, 'SemiAutoEnhance_Count', 0) or 0)

    def run(self):
        logger.hr('半自动强化', level=1)

        self.ui_ensure(page_dock)

        count = self._enhance_count()
        if count:
            logger.attr('强化数量上限', count)

        try:
            total, remain = self._enhance_handler(limit=count or None)
        finally:
            # 这一轮跑完就算结束，不留在调度里自动重复
            self.config.task_delay(minute=NO_AUTO_RUN_MINUTE)
            logger.info('[半自动强化] 本轮结束，已关闭自动重复；下次要用请再点「立即运行」')

        if total:
            logger.info(f'[半自动强化] 本次共强化 {total} 次，船坞剩余 {remain}')
        else:
            logger.info('[半自动强化] 没有可强化的舰船（检查「强化设置」的稀有度与附加索引）')

        raise TaskEnd('SemiAutoEnhance')
