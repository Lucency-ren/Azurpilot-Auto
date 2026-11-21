"""逐个强化逻辑离线自测（不连模拟器）。

验证 module/retire/enhancement.py 的新流程：
- _enhance_enter 使用「稀有度 R/SR/SSR/UR + 可强化 + 等级排序」筛选，
  并在调用期间临时打开 need_deselect（否则「全部/普通」不会被取消勾选）
- enhance_ships 每次只强化列表第一个，成功后重新取第一个
- 首艘失败 / 无船可强化 / 达到上限 三种结束条件
"""
import sys
from types import SimpleNamespace

sys.path.insert(0, r'D:\Alas\AzurPilot')

from module.retire import enhancement as E  # noqa: E402


class _Obj(E.Enhancement):
    """用固定上限替换 _retire_amount（原属性依赖 config）。"""

    @property
    def _retire_amount(self):
        return self._limit

    @property
    def _retire_keep_common_cv(self):
        # 原属性要读 config.is_task_enabled('GemsFarming')，测试里固定关闭
        return False


class _FakeSetting:
    def __init__(self):
        self.need_deselect = False


def make_obj(limit=3000):
    obj = _Obj.__new__(_Obj)
    obj._limit = limit
    obj.config = SimpleNamespace(
        Enhance_ShipToEnhance='all',
        Enhance_Sort='level',
        Enhance_Index='all',
        Enhance_Faction='all',
        # 五个独立的稀有度开关（普通默认关闭）
        Enhance_RarityCommon=False,
        Enhance_RarityRare=True,
        Enhance_RarityElite=True,
        Enhance_RaritySuperRare=True,
        Enhance_RarityUltra=True,
        # 附加索引是单选
        Enhance_ExtraIndex='enhanceable',
        # 每轮强化艘数上限，0 = 不限
        Enhance_Count=0,
        Retirement_RetireMode='one_click_retire',
    )
    obj.calls = []
    obj.ui_back = lambda page: obj.calls.append(('ui_back', page))
    obj._enhance_quit = lambda: obj.calls.append(('quit',))
    return obj


def test_filter_kwargs():
    obj = make_obj()
    setting = _FakeSetting()
    obj.dock_filter = setting
    rec = {}
    obj.dock_favourite_set = lambda **kw: rec.setdefault('fav', kw)
    obj.dock_enter_first = lambda **kw: True
    obj.appear = lambda *a, **kw: False

    def dock_filter_set(**kw):
        rec.update(kw)
        rec['need_deselect_during_call'] = setting.need_deselect

    obj.dock_filter_set = dock_filter_set

    assert obj._enhance_enter(favourite=False) is True
    assert rec['sort'] == 'level', rec
    assert rec['index'] == 'all', rec
    assert rec['faction'] == 'all', rec
    assert rec['rarity'] == ['rare', 'elite', 'super_rare', 'ultra'], rec
    assert rec['extra'] == 'enhanceable', rec
    assert rec['need_deselect_during_call'] is True, rec
    assert setting.need_deselect is False, '调用结束后必须还原 need_deselect'
    assert 'fav' not in rec, 'favourite=False 时不该动收藏筛选'
    print('OK filter kwargs')


def test_config_filter_applied():
    """配置里的五个筛选维度必须原样传给船坞筛选面板。"""
    obj = make_obj()
    obj.config.Enhance_Sort = 'rarity'
    obj.config.Enhance_Index = 'dd'
    obj.config.Enhance_Faction = 'sakura'
    obj.config.Enhance_RarityCommon = True
    obj.config.Enhance_RarityRare = False
    obj.config.Enhance_RarityElite = True
    obj.config.Enhance_RaritySuperRare = False
    obj.config.Enhance_RarityUltra = False
    obj.config.Enhance_ExtraIndex = 'no_limit'
    obj.dock_filter = _FakeSetting()
    rec = {}
    obj.dock_filter_set = lambda **kw: rec.update(kw)
    obj.appear = lambda *a, **kw: False
    obj.dock_enter_first = lambda **kw: True

    assert obj._enhance_enter() is True
    assert rec['sort'] == 'rarity', rec
    assert rec['index'] == 'dd', rec
    assert rec['faction'] == 'sakura', rec
    # 顺序固定为 普通→海上传奇，只保留勾上的
    assert rec['rarity'] == ['common', 'elite'], rec
    assert rec['extra'] == 'no_limit', '附加索引单选值应原样传下去'
    print('OK config filter applied')


def test_all_rarity_off():
    """五个开关全关时退回「全部」，不能把空列表丢给船坞筛选。"""
    obj = make_obj()
    for flag in ('RarityCommon', 'RarityRare', 'RarityElite', 'RaritySuperRare', 'RarityUltra'):
        setattr(obj.config, 'Enhance_' + flag, False)
    obj.dock_filter = _FakeSetting()
    rec = {}
    obj.dock_filter_set = lambda **kw: rec.update(kw)
    obj.appear = lambda *a, **kw: False
    obj.dock_enter_first = lambda **kw: True

    assert obj._enhance_enter() is True
    assert rec['rarity'] == 'all', rec
    print('OK all rarity off falls back to all')


def test_enter_empty():
    obj = make_obj()
    obj.dock_filter = _FakeSetting()
    obj.dock_filter_set = lambda **kw: None
    obj.appear = lambda *a, **kw: True
    obj.dock_enter_first = lambda **kw: (_ for _ in ()).throw(AssertionError('不应进入'))
    assert obj._enhance_enter() is False
    assert obj.dock_filter.need_deselect is False
    print('OK empty dock')


def test_stay_until_exhausted():
    """留在强化页：_enhance_choose 一次跑完，不再逐艘退回列表。"""
    obj = make_obj()
    obj._enhance_enter = lambda favourite=False: True
    obj._enhance_choose = lambda ship_count, stay=False, max_enhance=None: (False, 0, 3)
    total = obj.enhance_ships(favourite=False)
    assert total == 3, total
    # 只退一次船坞（_enhance_quit），循环里不再有中途 ui_back
    assert [c[0] for c in obj.calls] == ['quit'], obj.calls
    print('OK stay until exhausted')


def test_first_failure_stops():
    obj = make_obj()
    obj._enhance_enter = lambda favourite=False: True
    obj._enhance_choose = lambda ship_count, stay=False, max_enhance=None: (False, ship_count, 0)
    total = obj.enhance_ships(favourite=False)
    assert total == 0, total
    assert [c[0] for c in obj.calls] == ['quit'], obj.calls
    print('OK first failure stops')


def test_limit():
    obj = make_obj(limit=2)
    entered = []
    seen = {}

    def enter(favourite=False):
        entered.append(1)
        return True

    def choose(ship_count, stay=False, max_enhance=None):
        seen['ship_count'] = ship_count
        seen['stay'] = stay
        seen['max_enhance'] = max_enhance
        return True, 0, 2

    obj._enhance_enter = enter
    obj._enhance_choose = choose
    total = obj.enhance_ships(favourite=False)
    assert total == 2, total
    # 筛选只在进入时做一次，循环内不再重复设置（否则会反复点同一批按钮）
    assert len(entered) == 1, entered
    # 强化页内一直留在原地，因此必须把 stay 传下去；
    # ship_count 就是「本轮最多处理几艘」，max_enhance 不再限制强化次数
    assert seen == {'ship_count': 2, 'stay': True, 'max_enhance': None}, seen
    print('OK limit')


def test_count_option():
    """Enhance_Count > 0 时优先用它作为本轮艘数上限，0 时回落到 _retire_amount。"""
    obj = make_obj(limit=3000)
    obj.config.Enhance_Count = 7
    seen = {}

    def choose(ship_count, stay=False, max_enhance=None):
        seen['ship_count'] = ship_count
        return False, 0, 0

    obj._enhance_enter = lambda favourite=False: True
    obj._enhance_choose = choose
    obj.enhance_ships(favourite=False)
    assert seen['ship_count'] == 7, seen

    obj.config.Enhance_Count = 0
    obj.enhance_ships(favourite=False)
    assert seen['ship_count'] == 3000, seen
    print('OK count option')


class _Stub:
    """可配置返回值的占位对象。"""

    def __init__(self, value):
        self.value = value

    def match(self, *a, **kw):
        return self.value

    def __bool__(self):
        return self.value


def test_stay_mode_state_machine():
    """状态机层面验证：强化成功后留在当前舰船，强化不动时滑到下一艘。"""
    obj = make_obj()
    recommend = _Stub(True)
    confirm = _Stub(True)
    equip_confirm = _Stub(True)
    equip_confirm_2 = _Stub(False)
    empty_slot = _Stub(True)
    back = _Stub(True)
    get_items = _Stub(False)
    dock_check = _Stub(True)
    retire_equip = _Stub(False)

    saved = {}
    for name, value in (
        ('ENHANCE_RECOMMEND', recommend), ('ENHANCE_CONFIRM', confirm),
        ('EQUIP_CONFIRM', equip_confirm), ('EQUIP_CONFIRM_2', equip_confirm_2),
        ('EMPTY_ENHANCE_SLOT_PLUS', empty_slot), ('BACK_ARROW', back),
        ('GET_ITEMS_1', get_items), ('DOCK_CHECK', dock_check),
    ):
        saved[name] = getattr(E, name)
        setattr(E, name, value)

    # 每个元素代表「按推荐之后材料栏是否为空」：False=有材料(强化成功)，True=无材料(转 fail)
    script = [False, False, True, False, True]
    swipe_results = [True, False]
    state = {'idx': 0, 'swipes': 0, 'confirm_clicked': False}

    def slot_match(*a, **kw):
        i = min(state['idx'], len(script) - 1)
        state['idx'] += 1
        return script[i]

    empty_slot.match = slot_match

    obj.device = SimpleNamespace(
        image=None,
        click_record=[],
        screenshot=lambda: None,
        click_record_clear=lambda: None,
        click=lambda *a, **kw: None,
        long_click=lambda *a, **kw: None,
    )
    obj.equip_side_navbar_ensure = lambda upper=None, bottom=None: True
    obj.wait_until_appear = lambda *a, **kw: None
    obj.handle_popup_confirm = lambda *a, **kw: False
    obj.interval_clear = lambda *a, **kw: None
    obj.interval_reset = lambda *a, **kw: None
    obj._enhance_confirm = lambda *a, **kw: None

    def info_bar_count():
        i = min(max(state['idx'] - 1, 0), len(script) - 1)
        return 1 if script[i] else 0

    def appear_then_click(button, *a, **kw):
        if button is confirm:
            state['confirm_clicked'] = True
            return True
        return button is recommend

    def appear(button, *a, **kw):
        if button is equip_confirm and state['confirm_clicked']:
            state['confirm_clicked'] = False
            return True
        return False

    def equip_view_next(check_button=None, *a, **kw):
        i = state['swipes']
        state['swipes'] += 1
        return swipe_results[i] if i < len(swipe_results) else False

    obj.info_bar_count = info_bar_count
    obj.appear_then_click = appear_then_click
    obj.appear = appear
    obj.equip_view_next = equip_view_next

    try:
        result, ship_count, enhanced = obj._enhance_choose(
            ship_count=5, stay=True, max_enhance=10
        )
    finally:
        for name, value in saved.items():
            setattr(E, name, value)

    # 3 次成功（2 次在首舰 + 1 次在次舰），第 2 次滑动失败退出
    assert enhanced == 3, enhanced
    assert result is False, result
    assert ship_count == 4, ship_count
    print('OK stay mode state machine')


if __name__ == '__main__':
    test_filter_kwargs()
    test_config_filter_applied()
    test_all_rarity_off()
    test_enter_empty()
    test_stay_until_exhausted()
    test_first_failure_stops()
    test_limit()
    test_count_option()
    test_stay_mode_state_machine()
    print('ALL PASS')
