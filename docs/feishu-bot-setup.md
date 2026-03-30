# 飞书 Bot 配置指南

这份文档用于把一个飞书企业自建机器人配置成 **PoCo 可用**。

## Part I 机器人开通及权限配置

### 1

打开 <https://open.feishu.cn/app>，点击【创建企业自建应用】，填写【应用名称】和【应用描述】后完成创建。

### 2

点击菜单栏【添加应用能力】，选择【机器人】，点击添加。

### 3

点击菜单栏【权限管理】，点击【批量导入权限】，将如下 json 覆盖文本框后点击确认。

``` json
{
  "scopes": {
    "tenant": [
      "admin:app.category:update",
      "aily:file:read",
      "aily:file:write",
      "application:application.app_message_stats.overview:readonly",
      "application:application:self_manage",
      "application:bot.menu:write",
      "cardkit:card:read",
      "cardkit:card:write",
      "cardkit:template:read",
      "contact:user.employee_id:readonly",
      "corehr:file:download",
      "docs:document.content:read",
      "document_ai:bank_card:recognize",
      "document_ai:business_card:recognize",
      "document_ai:id_card:recognize",
      "event:ip_list",
      "im:app_feed_card:write",
      "im:chat",
      "im:chat.access_event.bot_p2p_chat:read",
      "im:chat.members:bot_access",
      "im:datasync.feed_card.time_sensitive:write",
      "im:message",
      "im:message.group_at_msg:readonly",
      "im:message.group_msg",
      "im:message.p2p_msg:readonly",
      "im:message:readonly",
      "im:message:send_as_bot",
      "im:message:update",
      "im:resource",
      "sheets:spreadsheet",
      "wiki:wiki:readonly"
    ],
    "user": [
      "aily:file:read",
      "aily:file:write",
      "im:chat.access_event.bot_p2p_chat:read"
    ]
  }
}
```

### 4

点击菜单栏【事件与回调】。

点击事件配置，配置订阅方式为【长连接】接受事件，点击保存。

点击添加事件，搜索 `im.message.receive_v1` 事件并添加、开通。

点击回调配置，配置订阅方式为【长连接】接受事件，点击保存。

点击添加事件，搜索 `card.action.trigger` 事件并添加、开通。

### 5 

至此完成权限配置，准备启用。

点击菜单栏【版本管理与发布】，点击创建版本，任意填写完成后点击【保存】后确认发布。

### 6

点击菜单栏【凭证与基础信息】，记录 `APP ID` 和 `APP Secret` 值。

在本地终端输入 `poco` 命令，按提示分别填入二者后，会看到 `poco` 重启。

## 验证

### 1

在 poco 中看到绿色的 `Relay: RUNNING` 和 `Config READY`。

### 2

打开飞书向刚刚创建的 `bot` 发送任意消息，会看到 `bot` 发来一张卡片。

至此，可以开始正式使用。
