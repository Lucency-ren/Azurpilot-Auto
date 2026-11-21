"""自律寻敌冻结画面看门狗的自测（不碰模拟器）。"""
import sys
import time

sys.path.insert(0, '.')

from module.combat.auto_search_combat import AutoSearchCombat
from module.exception import GameStuckError


class FakeImage:
    """只实现看门狗用到的那一点点 ndarray 接口。"""

    def __init__(self, value=0):
        self.value = value

    def __getitem__(self, item):
        return self

    def tobytes(self):
        return bytes([self.value % 256]) * 8


class FakeDevice:
    def __init__(self):
        self.clicks = []
        self.image = None

    def click(self, button, control_check=True):
        self.clicks.append(getattr(button, 'name', str(button)))

    def sleep(self, second):
        pass


class Fake(AutoSearchCombat):
    """只借用看门狗逻辑，绕开完整初始化。"""

    auto_search_idle_timeout = 0.35
    auto_search_no_progress_timeout = 5.0
    auto_search_stuck_timeout = 0.2
    auto_search_frozen_timeout = 0.6
    auto_search_stuck_max_attempt = 3
    _auto_search_stuck_timer = None
    _auto_search_frozen_timer = None
    _auto_search_idle_timer = None
    _auto_search_no_progress_timer = None

    def __init__(self, running=False):
        self.device = FakeDevice()
        self.running = running

    def is_auto_search_running(self):
        return self.running


def wait(seconds):
    time.sleep(seconds)


passed = 0
failed = []


def check(name, condition):
    global passed
    if condition:
        passed += 1
        print(f'  ok   {name}')
    else:
        failed.append(name)
        print(f'  FAIL {name}')


print('场景 A：认不出自律寻敌（冻结）→ 18s 点地图中央')
a = Fake(running=False)
check('未到点不动作', a._auto_search_stuck_check() is False)
check('未点击', a.device.clicks == [])
wait(0.25)
check('到点返回 True', a._auto_search_stuck_check() is True)
check('点了地图中央', a.device.clicks == ['AUTO_SEARCH_MAP_CENTER'])

print('场景 B：第二次 → 切换自律寻敌状态（单次点击）')
a.device.clicks.clear()
wait(0.25)
check('返回 True', a._auto_search_stuck_check() is True)
check('单次切换', a.device.clicks == ['AUTO_SEARCH_MAP_OPTION_ON'])

print('场景 C：显示运行中 → 快计时器续期，不误触')
b = Fake(running=True)
for _ in range(2):
    wait(0.15)
    b._auto_search_progress(running=True)
    check('运行中不动作', b._auto_search_stuck_check() is False)
    b.device.clicks.clear()
check('始终没点击', b.device.clicks == [])

print('场景 D：运行中僵死（一直无进展）→ 30s 兜底直接切自律寻敌')
c = Fake(running=True)
t0 = time.time()
fired = False
while time.time() - t0 < 1.6:
    if c._auto_search_stuck_check():
        fired = True
        break
    c._auto_search_progress(running=True)
    time.sleep(0.1)
check('慢计时器兜底触发', fired)
check('运行中不点地图中央，直接切自律寻敌', c.device.clicks == ['AUTO_SEARCH_MAP_OPTION_ON'])

print('场景 E：progress 完全重置')
d = Fake(running=False)
d._auto_search_stuck_check()
d._auto_search_progress()
check('计数清零', d.__dict__.get('_auto_search_stuck_attempt') is None)
check('慢计时器也重置', d._auto_search_frozen_timer is not None)

print('场景 F：连续唤醒超过上限 → GameStuckError')
e = Fake(running=False)
check('第一次调用只建计时器', e._auto_search_stuck_check() is False)
wait(0.25)
for _ in range(3):
    e._auto_search_stuck_check()
    wait(0.25)
try:
    e._auto_search_stuck_check()
    check('抛 GameStuckError', False)
except GameStuckError:
    check('抛 GameStuckError', True)

print('场景 G：画面一直在动（正常加载/打关）→ 等再久也不插手')
g = Fake(running=True)
g.device.image = FakeImage(0)
g._auto_search_stuck_check()
t0 = time.time()
acted = False
i = 0
while time.time() - t0 < 1.2:
    i += 1
    g.device.image = FakeImage(i)
    if g._auto_search_stuck_check():
        acted = True
        break
    time.sleep(0.05)
check('画面在动时从不动作', not acted)
check('画面在动时没有点击', g.device.clicks == [])

print('场景 H：画面一直在动，但自律寻敌一直不在运行态 → idle 超时点一次')
h = Fake(running=False)
h.device.image = FakeImage(0)
h._auto_search_stuck_check()
t0 = time.time()
acted = False
i = 0
while time.time() - t0 < 1.2:
    i += 1
    h.device.image = FakeImage(i)
    if h._auto_search_stuck_check():
        acted = True
        break
    time.sleep(0.05)
check('画面在动也会唤醒', acted)
check('点的是自律寻敌', h.device.clicks == ['AUTO_SEARCH_MAP_OPTION_ON'])

print('场景 I：按钮被误判成“运行中”+ 画面一直在动 → 硬兜底照样唤醒')
class FakeNoProgress(Fake):
    auto_search_no_progress_timeout = 0.4


j = FakeNoProgress(running=True)
j.device.image = FakeImage(0)
j._auto_search_stuck_check()
t0 = time.time()
acted = False
i = 0
while time.time() - t0 < 1.2:
    i += 1
    j.device.image = FakeImage(i)
    if j._auto_search_stuck_check():
        acted = True
        break
    time.sleep(0.05)
check('误判运行中也会唤醒', acted)
check('点的是自律寻敌', j.device.clicks == ['AUTO_SEARCH_MAP_OPTION_ON'])

print()
print(f'通过 {passed}，失败 {len(failed)}')
if failed:
    print('失败项:', failed)
    sys.exit(1)
