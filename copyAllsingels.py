#!/usr/bin/env python3
from telethon import TelegramClient, events
import os
import re
import datetime
import time
import asyncio

api_id = 29573949
api_hash = '585354ff26530edbf5af3351c648718f'

client = TelegramClient('session_all', api_id, api_hash)

# 监控的频道列表
source_channel_ids = [
    -1002491037353,  # Solana频道 (负数表示这是一个超级群组/频道)
    -1004628977967,   # BSC频道 (负数表示这是一个超级群组/频道)
    -1002228099557,   # ETH频道
    -1002246721161,   # Base 频道
    -4628977967
]
# 目标群组列表
target_group_ids = [
    -1002273219477,  # 第一个目标群组
    -4737354488       # 第二个目标群组
]

# 确保使用整数ID
source_channel_ids = [int(channel_id) for channel_id in source_channel_ids]
target_group_ids = [int(group_id) for group_id in target_group_ids]

# 频道名称映射，用于日志显示
channel_names = {
    -1002491037353: "Solana",
    -1004628977967: "BSC",
    -1002228099557: "ETH",
    -1002246721161: "Base",
    -4628977967: "BSC"
}

sent_addresses_file = 'sent_all_addresses.txt'

# 合约地址正则表达式 - 匹配多种格式（以太坊和Solana）
# 使用更精确的模式匹配消息中的合约地址
contract_pattern = re.compile(r'(?:合约|contract|合约):\s*([0-9a-zA-Z]{40,44})', re.IGNORECASE | re.MULTILINE)

# 添加一个额外的正则表达式来匹配更多格式的合约地址
contract_pattern_extra = re.compile(r'(?:合约|contract|合约):\s*([A-Za-z0-9]{32,44})', re.IGNORECASE | re.MULTILINE)

# 添加一个第三种正则表达式，专门匹配消息中的特定格式
contract_pattern_direct = re.compile(r'合约:\s*([A-Za-z0-9]{32,44})', re.IGNORECASE | re.MULTILINE)

# 已发送消息缓存
if os.path.exists(sent_addresses_file):
    with open(sent_addresses_file, 'r', encoding='utf-8') as f:
        sent_addresses = set(f.read().splitlines())
else:
    sent_addresses = set()

# 打印当前缓存的地址数量
print(f"当前缓存的合约地址数量: {len(sent_addresses)}")

# 热度统计相关变量
heat_data = {}  # 格式: {contract_address: {"count": 次数, "name": 币名}}
last_reset_time = None  # 上次重置热度的时间
REPORT_INTERVAL_MINUTES = 15  # 热度报告间隔，每15分钟

# 获取下一个报告时间
def get_next_report_time():
    now = datetime.datetime.now()
    # 计算下一个15分钟的时间点
    minutes = now.minute
    next_slot = ((minutes // REPORT_INTERVAL_MINUTES) + 1) * REPORT_INTERVAL_MINUTES
    if next_slot >= 60:  # 如果超过60分钟，进入下一个小时
        next_time = now.replace(minute=next_slot % 60, second=0, microsecond=0) + datetime.timedelta(hours=1)
    else:
        next_time = now.replace(minute=next_slot, second=0, microsecond=0)
    return next_time

# 重置热度统计
def reset_heat_data():
    global heat_data, last_reset_time
    heat_data = {}
    last_reset_time = datetime.datetime.now()
    print(f"热度统计已重置，时间: {last_reset_time}")

# 初始化热度统计
reset_heat_data()

# 更新热度统计
def update_heat_data(contract_address, coin_name=None):
    global heat_data
    if contract_address not in heat_data:
        heat_data[contract_address] = {"count": 0, "name": coin_name or contract_address}
    heat_data[contract_address]["count"] += 1
    heat_data[contract_address]["name"] = coin_name or heat_data[contract_address]["name"]

# 获取热度排名
def get_heat_ranking():
    sorted_heat = sorted(heat_data.items(), key=lambda x: x[1]["count"], reverse=True)
    return sorted_heat

# 生成热度报告消息
def generate_heat_report():
    ranking = get_heat_ranking()
    if not ranking:
        return f"过去{REPORT_INTERVAL_MINUTES}分钟内没有新的合约地址"
    
    report = f"🔥 {REPORT_INTERVAL_MINUTES}分钟热度排行 🔥\n\n"
    for i, (address, data) in enumerate(ranking, 1):
        report += f"{i}. {data['name']} - 热度: {data['count']}\n"
    
    report += f"\n统计时间: {last_reset_time.strftime('%Y-%m-%d %H:%M')} 至 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    return report

# 发送热度报告
async def send_heat_report():
    report = generate_heat_report()
    print(f"发送热度报告:\n{report}")
    
    # 向所有目标群组发送热度报告
    for target_id in target_group_ids:
        try:
            await client.send_message(target_id, report)
            print(f"成功发送热度报告到群组 {target_id}")
        except Exception as e:
            print(f"发送热度报告到群组 {target_id} 失败: {e}")
    
    # 重置热度统计
    reset_heat_data()

# 定时发送热度报告的任务
async def scheduled_heat_report():
    while True:
        # 计算到下一个报告时间的时间
        next_report_time = get_next_report_time()
        now = datetime.datetime.now()
        seconds_to_wait = (next_report_time - now).total_seconds()
        
        print(f"下一次热度报告将在 {next_report_time.strftime('%Y-%m-%d %H:%M')} 发送，等待 {seconds_to_wait:.2f} 秒")
        
        # 等待到下一个报告时间
        await asyncio.sleep(seconds_to_wait)
        
        # 发送热度报告
        await send_heat_report()

# 确保正确处理频道消息
@client.on(events.NewMessage)
async def handler(event):
    # 获取消息来源群组ID
    chat_id = event.chat_id
    
    # 打印所有收到的消息，无论是否来自监控频道
    print(f"收到消息，来源ID: {chat_id}, 类型: {type(chat_id)}")
    
    # 特别关注BSC群组
    if chat_id == -1004628977967:
        print(f"收到BSC群组消息: {event.raw_text[:100]}...")
        print(f"BSC消息详情: {event}")
    
    # 只处理来自指定频道的消息
    if chat_id not in source_channel_ids:
        print(f"消息来源 {chat_id} 不在监控列表中，跳过")
        return
        
    # 获取频道名称
    channel_name = channel_names.get(chat_id, f"未知频道({chat_id})")
    
    message_text = event.raw_text
    print(f"收到来自{channel_name}群组 {chat_id} 的消息：{message_text[:50]}...")
    
    # 尝试提取合约地址
    contract_match = contract_pattern.search(message_text)
    contract_match_extra = None
    contract_match_direct = None
    
    # 如果第一个正则表达式没有匹配，尝试使用第二个正则表达式
    if not contract_match:
        contract_match_extra = contract_pattern_extra.search(message_text)
    
    # 如果前两个正则表达式都没有匹配，尝试使用第三个正则表达式
    if not contract_match and not contract_match_extra:
        contract_match_direct = contract_pattern_direct.search(message_text)
    
    if contract_match or contract_match_extra or contract_match_direct:
        # 使用匹配到的正则表达式结果
        if contract_match:
            contract_address = contract_match.group(1)  # 提取匹配的合约地址
        elif contract_match_extra:
            contract_address = contract_match_extra.group(1)  # 提取匹配的合约地址
        else:
            contract_address = contract_match_direct.group(1)  # 提取匹配的合约地址
            
        print(f"来自{channel_name}群组 {chat_id} 的消息提取到合约地址：{contract_address}")
        
        # 标准化合约地址（转为小写）以确保更好的去重效果
        normalized_address = contract_address.lower()
        
        # 从消息中尝试提取币名
        coin_name = None
        coin_name_match = re.search(r'(?:名称|name):\s*([^\n,]+)', message_text, re.IGNORECASE)
        if coin_name_match:
            coin_name = coin_name_match.group(1).strip()
        
        # 更新热度统计
        update_heat_data(normalized_address, coin_name)
        print(f"更新热度统计: {normalized_address}, 币名: {coin_name}, 当前热度: {heat_data[normalized_address]['count']}")
        
        # 检查合约地址是否已发送
        if normalized_address not in sent_addresses:
            print(f"转发{channel_name}合约地址：{contract_address} 到所有目标群组")
            success = False
            try:
                # 向所有目标群组发送消息
                for target_id in target_group_ids:
                    await client.send_message(target_id, contract_address)
                    print(f"成功转发{channel_name}合约地址：{contract_address} 到群组 {target_id}")
                
                # 只有在至少一个群组发送成功时才记录
                success = True
                # 添加到内存中的集合（使用标准化后的地址）
                sent_addresses.add(normalized_address)
                # 写入文件（使用原始地址以保留格式）
                with open(sent_addresses_file, 'a', encoding='utf-8') as f:
                    f.write(contract_address + '\n')
                print(f"成功转发{channel_name}合约地址：{contract_address} 到所有群组，并已添加到去重缓存")
            except Exception as e:
                print(f"转发失败：{e}")
        else:
            print(f"{channel_name}合约地址 {contract_address} 已发送过，跳过。")
    else:
        print(f"来自{channel_name}群组 {chat_id} 的消息未找到合约地址，跳过转发。")



# 启动客户端
if __name__ == "__main__":
    with client:
        print("正在监听所有频道消息...")
        # 启动热度报告定时任务
        client.loop.create_task(scheduled_heat_report())
        client.run_until_disconnected()
