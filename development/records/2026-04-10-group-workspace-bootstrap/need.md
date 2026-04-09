# Need

## 背景

现在 `Create Project + Group` 已经能把 project 和群一起建出来，但用户建完群后如果群里还是空的，工作区仍然没有真正开始。

## 需求信号

- 用户已经接受 `DM -> create project -> create group` 这条主链
- 下一步需要让新群在创建完成后立即可见、可操作

## 场景

- 用户在 DM 里点击 `Create Project + Group`
- PoCo 建群成功
- 新群里立即出现第一张 workspace overview card

## 影响

这一步决定 project bootstrap 是否真正进入群工作区阶段。
