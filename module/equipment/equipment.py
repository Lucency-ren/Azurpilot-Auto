"""装备管理系统。

管理舰船装备的查看、更换和装备码操作。

功能：
- 装备界面的导航和检测
- 舰船视图的左右滑动切换
- 装备编辑按钮的状态管理
- 装备过滤器（正在装备中）的切换
- 装备码（Equipment Code）的导入导出

装备类型：
- 主炮（Main Gun）
- 副炮（Secondary Gun）
- 鱼雷（Torpedo）
- 防空炮（Anti-Air Gun）
- 设备（Auxiliary Device）

继承自 EquipmentCodeHandler，提供装备码处理能力。
"""

from module.base.button import ButtonGrid
from module.base.decorator import cached_property
from module.base.timer import Timer
from module.equipment.assets import *
from module.equipment.equipment_code import EquipmentCodeHandler
from module.logger import logger
from module.retire.assets import DOCK_CHECK, EQUIP_CONFIRM as RETIRE_EQUIP_CONFIRM
from module.ui.assets import BACK_ARROW
from module.ui.navbar import Navbar
from module.ui.switch import Switch

# 滑动参数
# 一张舰船卡约 145px 宽，250px 会一次跨过两艘，这里按「一次一艘」取值
SWIPE_DISTANCE = 150
SWIPE_RANDOM_RANGE = (-40, -20, 40, 20)
# 装备中过滤器开关
equipping_filter = Switch('Equiping_filter')
equipping_filter.add_state('on', check_button=EQUIPPING_ON)
equipping_filter.add_state('off', check_button=EQUIPPING_OFF)
# patch to handle both blue (folded) and orange (expanded) button
EQUIPMENT_OPEN.match = EQUIPMENT_OPEN.match_luma


class Equipment(EquipmentCodeHandler):
    """装备管理器。

    管理舰船装备的查看和更换操作。

    Attributes:
        equipment_has_take_on (bool): 是否已执行装备更换操作。
    """
    equipment_has_take_on = False

    def equipping_set(self, enable=False):
        if equipping_filter.set('on' if enable else 'off', main=self):
            self.wait_until_stable(SWIPE_AREA)

    def _ship_view_swipe(self, distance, check_button=EQUIPMENT_OPEN, max_same=2):
        """
        向左/右滑动切换舰船。

        Args:
            distance (int): 滑动距离，负值向左（下一艘）。
            check_button (Button): 滑动结束后等这个按钮出现再判定画面。
            max_same (int): 连续多少次滑动后画面仍未变化才判定「滑不动」。
                舰船图鉴里存在大量同名同立绘的重复舰船，只看画面颜色会把
                重复舰船误判成「没滑动」，因此画面没变时仍按「已切换」返回，
                让上层试一次强化；连续超过 max_same 次都没变化（滑到底回弹）
                才返回 False。

        Returns:
            bool: 是否成功切换到另一艘舰船。
        """
        self.handle_info_bar()
        SWIPE_CHECK.load_color(self.device.image)
        SWIPE_CHECK._match_init = True  # Disable ensure_template() on match(), allows ship to be properly determined
        # whether actually different or not

        # 逐艘强化时会连续滑动，同一个点击名累计到 device 的 12 次上限就会
        # 抛 GameTooManyClickError（2026-11-22 00:41 实际撞过），这里提前清账。
        # click_record 是 collections.deque（不是 dict），用 count 统计。
        record = getattr(self.device, 'click_record', None)
        if record is not None:
            try:
                same = record.count('SHIP_SWIPE')
            except (AttributeError, TypeError):
                same = 0
            if same >= 8:
                self.device.click_record_remove('SHIP_SWIPE')

        self.device.swipe_vector(vector=(distance, 0), box=SWIPE_AREA.area, random_range=SWIPE_RANDOM_RANGE,
                                 padding=0, duration=(0.1, 0.12), name='SHIP_SWIPE')
        skip_first_screenshot = True
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()
            if self.appear(check_button, offset=(30, 30)):
                break
            if self.appear(RETIRE_EQUIP_CONFIRM, offset=(30, 30)):
                logger.info('[装备-穿戴] 退役装备确认弹窗')
                return False
            # Popup when enhancing a NPC ship
            if self.handle_popup_confirm('SHIP_VIEW_SWIPE'):
                continue

        self.device.screenshot()

        if self.appear(RETIRE_EQUIP_CONFIRM, offset=(30, 30)):
            logger.info('[装备-穿戴] 退役装备确认弹窗')
            return False

        if SWIPE_CHECK.match(self.device.image):
            # 同名同立绘的重复舰船滑动后画面完全一样，不能直接判定「滑不动」。
            # 这里按「已切换」返回，让上层先试一次强化；连续 max_same 次都这样
            # 才认定真的到列表末尾（滑到底会回弹，画面一直不变）。
            same = getattr(self, '_ship_swipe_same', 0) + 1
            if same > max_same:
                logger.info(f'[装备-穿戴] 连续 {same} 次滑动画面未变化，判定已到列表末尾')
                self._ship_swipe_same = 0
                return False
            self._ship_swipe_same = same
            logger.info(f'[装备-穿戴] 滑动后画面未变化（可能是重复舰船），按新舰船处理 {same}/{max_same}')
            return True

        self._ship_swipe_same = 0
        if self.appear(check_button, offset=(30, 30)):
            logger.info('[装备-穿戴] 滑动检测到新舰船')
            return True
        return False

    def ship_view_next(self, check_button=EQUIPMENT_OPEN, max_same=2):
        return self._ship_view_swipe(distance=-SWIPE_DISTANCE, check_button=check_button, max_same=max_same)

    def ship_view_prev(self, check_button=EQUIPMENT_OPEN, max_same=2):
        return self._ship_view_swipe(distance=SWIPE_DISTANCE, check_button=check_button, max_same=max_same)

    def ship_info_enter(self, click_button, check_button=EQUIPMENT_OPEN, long_click=True, skip_first_screenshot=True):
        enter_timer = Timer(10)

        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            # End
            if self.appear(check_button, offset=(5, 5)):
                break

            # Long click accidentally became normal click, exit from dock
            if long_click:
                if self.appear(DOCK_CHECK, offset=(20, 20), interval=3):
                    logger.info(f'[装备-穿戴] 舰船信息进入 {DOCK_CHECK} -> {BACK_ARROW}')
                    self.device.click(BACK_ARROW)
                    continue
            if enter_timer.reached():
                if long_click:
                    self.device.long_click(click_button, duration=(1.5, 1.7))
                else:
                    self.device.click(click_button)
                enter_timer.reset()
            if self.handle_game_tips():
                continue

    @cached_property
    def _ship_side_navbar(self):
        """
        pry_sidebar 3 options
            research.
            equipment.
            detail.

        regular_sidebar 4 options
            enhancement.
            limit break.
            equipment.
            detail.

        retrofit_sidebar 5 options
            retrofit.
            enhancement.
            limit break.
            equipment.
            detail.
        """
        ship_side_navbar = ButtonGrid(
            origin=(21, 118), delta=(0, 94.5), button_shape=(60, 75), grid_shape=(1, 5), name='SHIP_SIDE_NAVBAR')

        return Navbar(grids=ship_side_navbar,
                      active_color=(247, 255, 173), active_threshold=221,
                      inactive_color=(140, 162, 181), inactive_threshold=221)

    def ship_side_navbar_ensure(self, upper=None, bottom=None):
        """
        Ensure able to transition to page
        Whether page has completely loaded is handled
        separately and optionally

        Args:
            upper (int):
                pry|regular|retrofit
                1|N/A|N/A for research.
                N/A|N/A|1 for retrofit.
                N/A|1|2   for enhancement.
                N/A|2|3   for limit break.
                2|3|4     for equipment.
                3|4|5     for detail.
            bottom (int):
                pry|regular|retrofit
                3|N/A|N/A for research.
                N/A|N/A|5 for retrofit.
                N/A|4|4   for enhancement.
                N/A|3|3   for limit break.
                2         for equipment.
                1         for detail.

        Returns:
            bool: if side_navbar set ensured
        """
        if self._ship_side_navbar.get_total(main=self) == 3:
            if upper == 1 or bottom == 3:
                logger.warning('[装备-穿戴] 不支持跳转到 "research"')
                return False

        if self._ship_side_navbar.set(self, upper=upper, bottom=bottom):
            return True
        return False

    def equip_view_next(self, check_button=EQUIPMENT_OPEN, max_same=2):
        return self.ship_view_next(check_button=check_button, max_same=max_same)

    def equip_view_prev(self, check_button=EQUIPMENT_OPEN):
        return self.ship_view_prev(check_button=check_button)

    def equip_enter(self, click_button, check_button=EQUIPMENT_OPEN, long_click=True, skil_first_screenshot=True):
        return self.ship_info_enter(
            click_button=click_button,
            check_button=check_button,
            long_click=long_click,
            skip_first_screenshot=skil_first_screenshot
        )

    def equip_side_navbar_ensure(self, upper=None, bottom=None):
        return self.ship_side_navbar_ensure(upper=upper, bottom=bottom)

    def ship_equipment_take_off(self, name=None):
        self.code_clear(name=name)

    def ship_equipment_take_on(self, name=None):
        self.code_apply(name=name)

    def _equip_take_off_one(self, skip_first_screenshot=True):
        logger.info('[装备-穿戴] 装备卸下')
        bar_timer = Timer(5)
        off_timer = Timer(5)
        confirm_timer = Timer(5)

        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if off_timer.started() and self.info_bar_count():
                break

            if self.handle_storage_full():
                continue

            if confirm_timer.reached() and self.handle_popup_confirm('EQUIPMENT_TAKE_OFF'):
                confirm_timer.reset()
                off_timer.reset()
                bar_timer.reset()
                continue

            if off_timer.reached():
                if not self.info_bar_count() and self.appear_then_click(EQUIP_OFF, offset=(20, 20)):
                    off_timer.reset()
                    bar_timer.reset()
                    continue

            if bar_timer.reached():
                if self.appear(EQUIPMENT_OPEN, offset=(20, 20)) and not self.appear(EQUIP_OFF, offset=(20, 20)):
                    self.device.click(EQUIPMENT_OPEN)
                    bar_timer.reset()
                    continue

        logger.info('[装备-穿戴] 装备卸下完成')

    def equipment_take_off(self, enter, out, fleet):
        """
        Args:
            enter (Button): Long click to edit equipment.
            out (Button): Button to confirm exit success.
            fleet (list[int]): list of equipment record. [3, 1, 1, 1, 1, 1]
        """
        logger.hr('[装备-穿戴] 装备卸下')
        self.equip_enter(enter)

        for index in '9'.join([str(x) for x in fleet if x > 0]):
            index = int(index)
            if index == 9:
                self.equip_view_next()
            else:
                self._equip_take_off_one()
                self.ui_click(click_button=EQUIPMENT_CLOSE, check_button=EQUIPMENT_OPEN, offset=None)

        self.ui_back(out)
        self.equipment_has_take_on = False

    def _equip_take_on_one(self, index, skip_first_screenshot=True):
        logger.info('[装备-穿戴] 装备预设装上')
        bar_timer = Timer(5)
        on_timer = Timer(5)

        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()

            if on_timer.started() and self.info_bar_count():
                break

            if bar_timer.reached() and not self.appear(EQUIP_1, offset=10):
                self.device.click(EQUIPMENT_OPEN)
                bar_timer.reset()
                continue

            if on_timer.reached() and self.appear(EQUIP_1, offset=10) and not self.info_bar_count():
                if index == 1:
                    self.device.click(EQUIP_1)
                elif index == 2:
                    self.device.click(EQUIP_2)
                elif index == 3:
                    self.device.click(EQUIP_3)

                on_timer.reset()
                bar_timer.reset()
                continue

        logger.info('[装备-穿戴] 装备装上完成')

    def equipment_take_on(self, enter, out, fleet):
        """
        Args:
            enter (Button): Long click to edit equipment.
            out (Button): Button to confirm exit success.
            fleet (list[int]): list of equipment record. [3, 1, 1, 1, 1, 1]
        """
        logger.hr('[装备-穿戴] 装备装上')
        self.equip_enter(enter)

        for index in '9'.join([str(x) for x in fleet if x > 0]):
            index = int(index)
            if index == 9:
                self.equip_view_next()
            else:
                self._equip_take_on_one(index=index)
                self.ui_click(click_button=EQUIPMENT_CLOSE, check_button=EQUIPMENT_OPEN, offset=None)

        self.ui_back(out)
        self.equipment_has_take_on = True
