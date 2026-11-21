"""
舰船强化系统。

提供船坞中舰船装备强化的完整流程，包括按舰船类型分类强化、
推荐材料选择、强化确认、失败重试等操作。通过 DFA（确定性有限自动机）
状态机模式驱动强化流程，自动处理战斗中、无材料等异常情况。

当退役模式为 enhance 时，优先执行强化；强化完成或失败后
可回退到退役流程。
"""

import cv2

import module.config.server as server
from module.base.timer import Timer
from module.base.utils import area_pad
from module.combat.assets import GET_ITEMS_1
from module.exception import GameStuckError, ScriptError
from module.logger import logger
from module.ocr.ocr import DigitCounter
from module.retire.assets import *
from module.retire.dock import Dock
from module.ui.assets import BACK_ARROW

VALID_SHIP_TYPES = ['dd', 'ss', 'cl', 'ca', 'bb', 'cv', 'repair', 'others']

# 自动强化的筛选条件全部来自配置「强化设置」：
#   排序 / 索引 / 阵营 / 稀有度 / 附加索引，与游戏船坞筛选面板一一对应。

if server.server != 'jp':
    OCR_DOCK_AMOUNT = DigitCounter(
        DOCK_AMOUNT, letter=(255, 255, 255), threshold=192)
else:
    OCR_DOCK_AMOUNT = DigitCounter(
        DOCK_AMOUNT, letter=(201, 201, 201), threshold=192)


class Enhancement(Dock):
    """舰船强化处理器。

    继承 Dock 类，在船坞页面中执行装备强化操作。
    使用 DFA 状态机模式管理强化流程，支持按舰船类型
    分类处理、推荐材料自动选择、强化失败后的自动翻页重试。

    Attributes:
        _retire_amount (property): 根据退役模式配置计算的退役数量上限。
    """
    # 图鉴里有大量同名同立绘的重复舰船，滑动后画面可能完全一样。
    # 这里允许连续这么多次「画面没变」才判定滑到列表末尾，避免一遇到
    # 重复舰船就结束本轮强化。
    enhance_swipe_max_same = 6

    @property
    def _retire_amount(self):
        if self.config.Retirement_RetireMode == 'one_click_retire':
            return 3000
        if self.config.Retirement_RetireMode == 'old_retire':
            if self.config.OldRetire_RetireAmount == 'retire_all':
                return 3000
            if self.config.OldRetire_RetireAmount == 'retire_10':
                return 10
        return 3000

    @property
    def _retire_keep_common_cv(self):
        """
        Returns:
            str: "any" or specific ship name, or empty string if GemsFarming is not enabled
        """
        if not self.config.is_task_enabled('GemsFarming'):
            return ''
        return self.config.cross_get('GemsFarming.GemsFarming.CommonCV', default='any')

    def _enhance_enter(self, favourite=False):
        """
        按配置的筛选条件进入列表第一个舰船。

        五个维度与游戏船坞筛选面板一一对应，全部来自配置：
        排序 / 索引 / 阵营 / 稀有度 / 附加索引。

        Pages:
            in: page_dock
            out: page_ship_enhance

        Returns:
            bool: False with filter applied resulting
                  in empty dock.
                  Otherwise true with at least 1 card
                  available to be picked.
        """
        if favourite:
            self.dock_favourite_set(enable=True, wait_loading=False)

        # 配置里新增的五个筛选维度；首次升级前生成的配置可能还没有这些键，
        # 取值失败时退回旧的默认筛选（等级升序 / 不限 / 可强化）。
        sort = getattr(self.config, 'Enhance_Sort', None) or 'level'
        index = getattr(self.config, 'Enhance_Index', None) or 'all'
        faction = getattr(self.config, 'Enhance_Faction', None) or 'all'
        # 稀有度是五个独立开关（RarityCommon/Rare/Elite/SuperRare/Ultra），
        # 按 普通→海上传奇 的顺序拼回船坞筛选要的列表。
        rarity = [
            rarity_key
            for rarity_key, config_key in (
                ('common', 'Enhance_RarityCommon'),
                ('rare', 'Enhance_RarityRare'),
                ('elite', 'Enhance_RarityElite'),
                ('super_rare', 'Enhance_RaritySuperRare'),
                ('ultra', 'Enhance_RarityUltra'),
            )
            if getattr(self.config, config_key, False)
        ]
        if not rarity:
            logger.warning('[退役-强化] 五个稀有度开关都没开，本轮按「全部」筛选')
            rarity = 'all'
        elif len(rarity) == 1:
            rarity = rarity[0]
        # 附加索引是单选下拉，直接用配置值。
        extra = getattr(self.config, 'Enhance_ExtraIndex', None) or 'enhanceable'
        if isinstance(extra, list):
            extra = extra[0] if extra else 'enhanceable'

        # 船坞筛选默认只「点亮」需要的选项、不「关闭」多余的选项，
        # 这里必须先把多余的选项取消勾选，筛选才会真正生效。
        setting = self.dock_filter
        need_deselect = setting.need_deselect
        setting.need_deselect = True
        try:
            self.dock_filter_set(
                sort=sort,
                index=index,
                faction=faction,
                rarity=rarity,
                extra=extra,
            )
        finally:
            setting.need_deselect = need_deselect

        if self.appear(DOCK_EMPTY, offset=(30, 30)):
            return False

        return self.dock_enter_first()

    def _enhance_quit(self):
        """
        Pages:
            in: page_ship_enhance
            out: page_dock
        """
        self.ui_back(DOCK_CHECK)
        self.dock_favourite_set(enable=False, wait_loading=False)
        self.dock_filter_set()

    def _enhance_confirm(self, skip_first_screenshot=True):
        """
        Pages:
            in: EQUIP_CONFIRM
            out: page_ship_enhance, without info_bar
        """

        confirm_timer = Timer(1.5, count=3).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if self.appear_then_click(EQUIP_CONFIRM, offset=(30, 30), interval=3):
                confirm_timer.reset()
                continue
            if self.appear_then_click(EQUIP_CONFIRM_2, offset=(30, 30), interval=3):
                confirm_timer.reset()
                continue
            if self.appear(GET_ITEMS_1, interval=2):
                self.device.click(GET_ITEMS_1_RETIREMENT_SAVE)
                self.interval_reset(ENHANCE_CONFIRM)
                confirm_timer.reset()
                continue

            # End
            if self.appear(ENHANCE_CONFIRM, offset=(30, 30)):
                if confirm_timer.reached():
                    break
            else:
                confirm_timer.reset()

    def _enhance_recover(self, skip_first_screenshot=True):
        """
        强化流程异常后的界面恢复。

        异常可能打断强化确认后的装备拆解弹窗（信息）或强化结算动画，
        这类模态弹窗仅点返回键无法关闭；先按强化收尾流程依次处理
        拆解确认（默认不拆解，装备入库）与奖励收取，界面回到船坞列表
        后结束，由调用方退出船坞。恢复超时说明界面不可自行恢复，
        抛出 GameStuckError 交由调度器重启游戏兜底。

        Pages:
            in: 舰船强化页 / 装备拆解弹窗 / 船坞列表
            out: page_dock（DOCK_CHECK 可见，船坞未退出）

        Raises:
            GameStuckError: 恢复超时（约 60 秒）仍未回到船坞列表。
        """
        logger.info('强化异常恢复')
        timeout = Timer(60, count=60).start()
        confirm_timer = Timer(2, count=4).start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if timeout.reached():
                logger.warning('[退役-强化] 异常恢复超时')
                raise GameStuckError('强化异常恢复超时')

            # 强化确认后的装备拆解弹窗，点击确定（默认不拆解，装备入库）
            if self.appear_then_click(EQUIP_CONFIRM, offset=(30, 30), interval=3):
                confirm_timer.reset()
                continue
            if self.appear_then_click(EQUIP_CONFIRM_2, offset=(30, 30), interval=3):
                confirm_timer.reset()
                continue
            # 强化结果收取
            if self.appear(GET_ITEMS_1, interval=2):
                self.device.click(GET_ITEMS_1_RETIREMENT_SAVE)
                confirm_timer.reset()
                continue
            # 其他通用确认弹窗
            if self.handle_popup_confirm('ENHANCE_RECOVER'):
                confirm_timer.reset()
                continue

            # 已回到船坞列表，等待界面稳定后结束
            if self.appear(DOCK_CHECK, offset=(20, 20)):
                if confirm_timer.reached():
                    break
                continue

            # 单舰强化页，退回船坞列表
            confirm_timer.reset()
            if self.appear_then_click(BACK_ARROW, offset=(30, 30), interval=3):
                continue

    def _enhance_get_deselect_cv(self, first_slot=False):
        """
        Args:
            first_slot: True to check in first slot only, False to check in all slots

        Returns:
            Button | None: Button of common rarity CV to de-select, or None if not found
        """
        cv = self._retire_keep_common_cv
        if not cv:
            return None
        dict_template = {
            'bogue': TEMPLATE_ENHANCE_BOGUE,
            'hermes': TEMPLATE_ENHANCE_HERMES,
            'langley': TEMPLATE_ENHANCE_LANGLEY,
            'ranger': TEMPLATE_ENHANCE_RANGER,
        }
        # CommonCV 配置值为 custom/any/eagle 时不能直接作为舰名索引，
        # 需先展开为有效舰名集合，与退役流程的解析语义保持一致
        if cv == 'custom':
            # 自定义保留：按 GemsFarming_CommonCVFilter 展开有效舰名
            filter_string = self.config.cross_get(
                'GemsFarming.GemsFarming.CommonCVFilter', default='bogue > ranger > langley > hermes')
            names = [s.strip().lower() for s in str(filter_string).split('>')]
            dict_template = {name: dict_template[name] for name in names if name in dict_template}
            if not dict_template:
                logger.warning('[退役-强化] CommonCVFilter 无有效舰名，回退为保留全部普通航母')
                dict_template = {
                    'bogue': TEMPLATE_ENHANCE_BOGUE,
                    'hermes': TEMPLATE_ENHANCE_HERMES,
                    'langley': TEMPLATE_ENHANCE_LANGLEY,
                    'ranger': TEMPLATE_ENHANCE_RANGER,
                }
        elif cv == 'eagle':
            # 白鹰阵营不含皇家航母 hermes
            dict_template.pop('hermes', None)
        elif cv != 'any' and cv in dict_template:
            dict_template = {cv: dict_template[cv]}

        if first_slot:
            # outer pad 22 px reaches slot edge
            area = area_pad(EMPTY_ENHANCE_SLOT_PLUS.area, pad=-22)
        else:
            area = ENHANCE_AREA_FULL.area
        image = self.image_crop(area, copy=False)

        for cv, template in dict_template.items():
            sim, button = template.match_result(image)
            if sim > 0.85:
                button = button.move(area[:2])
                return Button(area=button.area, color=button.color, button=button.area,
                              name=f'TEMPLATE_ENHANCE_{cv.upper()}_RETIRE')

        return None

    def _enhance_deselect_cv(self):
        """
        De-select common rarity CV from enhance material slots
        """
        cv = self._enhance_get_deselect_cv()
        if cv is None:
            return

        logger.info(f'Enhance de-select common CV')
        # get cv slot, outer pad from matched center
        area = cv.area
        center = ((area[0] + area[2]) / 2, (area[1] + area[3]) / 2)
        radius = abs(EMPTY_ENHANCE_SLOT_PLUS.area[3] - EMPTY_ENHANCE_SLOT_PLUS.area[1]) / 2
        radius = radius + 22
        search = (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius)

        self.interval_clear(ENHANCE_RECOMMEND, interval=2)
        EMPTY_ENHANCE_SLOT_PLUS.ensure_template()
        for _ in self.loop():
            image = self.image_crop(search, copy=False)
            result = cv2.matchTemplate(EMPTY_ENHANCE_SLOT_PLUS.image, image, cv2.TM_CCOEFF_NORMED)
            _, similarity, _, _ = cv2.minMaxLoc(result)
            if similarity > 0.85:
                logger.info(f'Enhance de-select common CV done')
                break

            # Accidentally entered dock
            if self.appear(DOCK_CHECK, offset=(20, 20), interval=3):
                logger.info(f'{DOCK_CHECK} -> {BACK_ARROW}')
                self.device.click(BACK_ARROW)
                continue
            if self.appear(ENHANCE_RECOMMEND, offset=(5, 5), interval=5):
                self.device.click(cv)
                continue

    def _enhance_choose(self, ship_count, skip_first_screenshot=True, stay=False, max_enhance=None):
        """
        Refactor the implementation.
        Divided the enhancement process into
        several state functions. Use a DFA method
        to call those functions according to
        current state. Each state corresponds to
        a function with the same name.

        Pages:
            in: page_ship_enhance
            out: page_ship_enhance

        Args:
            ship_count (int): ship_count, must be
            non-zero positive integer
            stay (bool): 强化成功后留在强化页继续处理当前舰船，
            当前舰船强化不动时自动向左滑动切到下一艘
            max_enhance (int): 本次调用允许的最大强化次数

        Returns:
            tuple(bool, int, int): (是否成功过, 剩余 ship_count, 强化次数)
        """
        need_to_skip: bool = False
        enhanced: int = 0
        navbar_retry: int = 0
        # 「按推荐」只点一次：材料栏加载需要时间，加载期间没看到材料
        # 不代表点击失败，等这个计时器到点才补点一次，避免每艘船都点两下
        recommend_timer = Timer(6)

        def state_enhance_check():
            # Check the base case, switch to ready if enhancement can continue
            nonlocal need_to_skip, navbar_retry
            need_to_skip = False
            if ship_count <= 0:
                logger.info(
                    '[退役-强化] 已达到最大检查次数，退出当前分类')
                return "state_enhance_exit"
            if not self.equip_side_navbar_ensure(bottom=4):
                # 停留在强化页时导航栏偶发识别不到，但状态不变不会累计
                # 振荡计数，需要单独的连续失败上限避免死等
                navbar_retry += 1
                if navbar_retry > 20:
                    logger.warning('[退役-强化] 强化页侧边导航连续 20 次未识别，退出当前分类')
                    return "state_enhance_exit"
                return "state_enhance_check"
            navbar_retry = 0

            self.wait_until_appear(ENHANCE_RECOMMEND, offset=(
                5, 5), skip_first_screenshot=True)
            return "state_enhance_ready"

        def state_enhance_ready():
            # Wait until ENHANCE_RECOMMEND appears
            # interval 需大于材料栏加载耗时，否则加载慢时会连点推荐，
            # 累积的点击会触发网格防连击检测导致强化被误判失败
            if self.appear_then_click(ENHANCE_RECOMMEND, offset=(5, 5), interval=2):
                logger.info('按推荐设置强化材料')
                recommend_timer.reset()
                return "state_enhance_recommend"

            return "state_enhance_ready"

        def state_enhance_recommend():
            # Judge if enhance material appeared
            if not EMPTY_ENHANCE_SLOT_PLUS.match(self.device.image, offset=(20, 20)):
                if self._retire_keep_common_cv:
                    # 若第一格为普通 CV 且第二格为空，视为无材料，
                    # 避免"推荐→反选"死循环；第二格在左侧 92px 处
                    if EMPTY_ENHANCE_SLOT_PLUS.match(self.device.image, offset=(72, -20, 112, 20)) \
                            and self._enhance_get_deselect_cv(first_slot=True):
                        logger.info('[退役-强化] 仅 1 个普通 CV 材料，视为无强化材料')
                        logger.info('[退役-强化] 强化失败，滑动到下一艘舰船（如可行）')
                        return "state_enhance_fail"
                    # 反选已填充的普通 CV
                    self._enhance_deselect_cv()

                logger.info('找到材料，尝试强化...')
                return "state_enhance_attempt"
            elif self.info_bar_count():
                logger.info('未找到强化材料')
                logger.info('[退役-强化] 强化失败，滑动到下一艘舰船（如可行）')
                return "state_enhance_fail"
            elif recommend_timer.reached():
                # 等了 6 秒材料栏还是空的，说明那一下推荐没生效，补点一次
                logger.info('[退役-强化] 推荐材料 6 秒未出现，重新点击推荐')
                return "state_enhance_ready"

            return "state_enhance_recommend"

        def state_enhance_attempt():
            # Wait until ENHANCE_CONFIRM appears
            if (self.appear_then_click(ENHANCE_CONFIRM, offset=(5, 5), interval=0.3)
                    or self.appear(EQUIP_CONFIRM, offset=(30, 30))
                    or self.info_bar_count()
                    or self.handle_popup_confirm('ENHANCE')):
                return "state_enhance_confirm"

            return "state_enhance_attempt"

        def state_enhance_confirm():
            # Succeeded if EQUIP_CONFIRM appeared, otherwise failed
            if self.appear(EQUIP_CONFIRM, offset=(30, 30)):
                logger.info('强化成功')
                self._enhance_confirm()
                return "state_enhance_success"
            elif self.info_bar_count():
                logger.info(
                    '[退役-强化] 强化不可行，舰船当前在战斗中，滑动到下一艘舰船（如可行）')
                nonlocal need_to_skip
                need_to_skip = True
                return "state_enhance_fail"
            elif self.handle_popup_confirm('ENHANCE'):
                logger.info('尝试临时舰船')
                return "state_enhance_confirm"

            return "state_enhance_attempt"

        def state_enhance_fail():
            # Avoid a misjudgement caused by broken network
            if self.appear(EQUIP_CONFIRM, offset=(30, 30)):
                return "state_enhance_confirm"

            # Try to swipe to next
            if self.equip_view_next(check_button=ENHANCE_RECOMMEND, max_same=self.enhance_swipe_max_same):
                if not need_to_skip:
                    nonlocal ship_count
                    ship_count -= 1
                return "state_enhance_check"
            else:
                # Avoid a misjudgement caused by broken network
                if self.appear(EQUIP_CONFIRM, offset=(30, 30)):
                    return "state_enhance_confirm"
                else:
                    logger.info('滑动失败，退出当前分类')
                    return "state_enhance_exit"

        def state_enhance_success():
            # 成功强化一艘即清空点击记录，正常连强多艘时点击集中在右下角同一
            # 网格，若跨轮累积会触发网格防连击检测，把正常流程误判为强化失败
            nonlocal enhanced, ship_count
            self.device.click_record_clear()
            enhanced += 1
            # 成功一次就是真实进展，清空振荡计数，避免连强多艘被计成死循环
            state_list.clear()
            logger.info(f'[退役-强化] 累计强化 {enhanced} 次')
            if not stay:
                return True
            if max_enhance is not None and enhanced >= max_enhance:
                logger.info('[退役-强化] 达到本轮强化上限，结束')
                return True
            if ship_count <= 0:
                return True
            # 留在强化页继续强化当前舰船；强化不动时由 state_enhance_fail
            # 向左滑动切到下一艘（滑动失败才退出本轮）
            return "state_enhance_check"

        def state_enhance_exit():
            return False

        # 显式字典映射，替代 locals()[state]()。
        # Python 3.14 PEP 667 改变了 locals() 行为，使用 nonlocal 的嵌套函数
        # 可能不在 locals() 快照中，导致 KeyError。
        state_functions = {
            "state_enhance_check": state_enhance_check,
            "state_enhance_ready": state_enhance_ready,
            "state_enhance_recommend": state_enhance_recommend,
            "state_enhance_attempt": state_enhance_attempt,
            "state_enhance_confirm": state_enhance_confirm,
            "state_enhance_fail": state_enhance_fail,
            "state_enhance_success": state_enhance_success,
            "state_enhance_exit": state_enhance_exit,
        }

        state = "state_enhance_check"
        state_list = []
        while isinstance(state, str):
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()
            logger.info(f'调用状态函数: {state}')

            if state == "state_enhance_check":
                # Avoid too_many_click exception caused by multiple tries without material
                if state_list[-2:] == ["state_enhance_recommend", "state_enhance_fail"]:
                    while self.device.click_record and (self.device.click_record[-1] in ['ENHANCE_RECOMMEND', 'EQUIP_SWIPE', 'SHIP_SWIPE']):
                        self.device.click_record.pop()
                # Avoid too_many_click exception caused by enhancement failure on in-battle ships
                elif state_list[-3:] == ["state_enhance_attempt", "state_enhance_confirm", "state_enhance_fail"]:
                    while self.device.click_record and (self.device.click_record[-1] in ['ENHANCE_RECOMMEND', 'EQUIP_SWIPE', 'SHIP_SWIPE', 'ENHANCE_CONFIRM']):
                        self.device.click_record.pop()
                state_list.clear()
            # 记录状态迁移而非轮询迭代：等待装填动画、确认弹窗加载期间
            # 连续相同状态（ready、attempt 反复轮询）只记一次，
            # 避免正常等待被误判为死循环、强化在即将成功前被中断；
            # 状态来回切换不推进的真实振荡仍会被上限拦截
            if not state_list or state_list[-1] != state:
                state_list.append(state)
                if len(state_list) > 30:
                    logger.critical(f'[退役] 状态机循环次数过多: {state_list}')
                    raise GameStuckError('状态机循环次数过多')

            # 字典查找和函数调用分开，避免函数内部抛出的 KeyError
            # 被误判为"未知状态函数"
            if state not in state_functions:
                logger.warning(f'未知的状态函数: {state}')
                raise ScriptError(f'未知的状态函数: {state}')
            state = state_functions[state]()

        return bool(state), ship_count, enhanced

    def enhance_ships(self, favourite=None, limit=None):
        """
        逐个强化：进入筛选结果里的第一艘舰船后留在强化页，把这艘强化到
        不能强化为止，再向左滑动切到下一艘。

        判定无法强化时（无材料 / 战斗中 / 已达强化上限）由
        state_enhance_fail 直接滑动到下一艘；滑不动说明没有下一艘可强化
        舰船，本轮结束并退回船坞列表。

        筛选条件来自配置里的五个维度（排序/索引/阵营/稀有度/附加索引），
        只在进入时设置一次：船坞筛选是常驻状态，每强化一艘就重设一遍会
        反复点同一批按钮（「全部」/「前排先锋」识别摇摆），很快撞上点击保护。

        Pages:
            in: page_dock
            out: page_dock

        Args:
            favourite (bool):

        Returns:
            int: total enhanced
        """
        if favourite is None:
            favourite = self.config.Enhance_ShipToEnhance == 'favourite'

        logger.hr('逐个强化')
        # 每轮强化艘数上限：0 = 一直强化到没有可强化舰船为止
        # limit 由调用方覆盖（半自动强化任务用自己的 Count）
        if limit is None:
            count = int(getattr(self.config, 'Enhance_Count', 0) or 0)
            limit = count if count > 0 else max(int(self._retire_amount), 1)
        else:
            limit = max(int(limit), 1)
        logger.info(f'[退役-强化] 本轮上限 {limit} 艘')

        if not self._enhance_enter(favourite=favourite):
            logger.info('[退役-强化] 船坞中已无可强化舰船')
            self._enhance_quit()
            return 0

        result, ship_count, enhanced = self._enhance_choose(
            ship_count=limit, stay=True, max_enhance=None
        )

        self._enhance_quit()

        if enhanced:
            logger.info(f'[退役-强化] 本轮共强化 {enhanced} 次')
        else:
            logger.info('[退役-强化] 首个舰船强化失败（无材料或不可强化），结束本轮强化')

        return enhanced

    def _enhance_handler(self, limit=None):
        """
        Pages:
            in: RETIRE_APPEAR
            out:

        Returns:
            tuple(int, int): (enhance turn count, remaining dock amount)

        Pages:
            in: DOCK_CHECK
            out: the page before retirement popup
        """
        total = self.enhance_ships(limit=limit)
        _, remain, _ = OCR_DOCK_AMOUNT.ocr(self.device.image)

        self.dock_quit()
        self.config.DOCK_FULL_TRIGGERED = True

        return total, remain
