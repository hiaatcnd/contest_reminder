import nonebot
from nonebot import on_command, CommandSession
from aiocqhttp.exceptions import Error as CQHttpError
from datetime import datetime, timedelta, timezone
import pytz
import requests
import time

DEFALUT_SITES = {'codeforces.com', 'atcoder.jp',
                 'yukicoder.me', 'topcoder.com/community'}

all_list = set()
admins = {1023964019}
groups = {}
last_time = {}

cache_contests = []


@on_command("addq")
async def add_admin(session: CommandSession):
    global admins
    if session.event.user_id == 1023964019:
        qq = session.current_arg_text.strip()
        if qq and qq.isdigit():
            admins.add(int(qq))
            await session.send("添加成功：", qq)
        else:
            await session.send("添加失败，请重试")


@on_command("update")
async def update(session: CommandSession):
    if session.event.user_id == 1023964019:
        await update_all_list(must=1)


@on_command("addg")
async def add_group(session: CommandSession):
    global admins
    global groups
    if session.event.user_id in admins:
        group = session.current_arg_text.strip()
        if not group and session.event.detail_type == "group":  # 添加这个群
            group = str(session.event.group_id)
        if group and group.isdigit():
            group = int(group)
            if group not in groups:
                groups[group] = DEFALUT_SITES.copy()
                last_time[group] = None
                await session.send('激活群成功：{}'.format(group))
            else:
                await session.send("已激活该群")
        else:
            await session.send("激活失败，请重试")


@on_command("showsite")
async def show_sites(session: CommandSession):
    global groups
    if session.event.detail_type == "group":
        group = session.event.group_id
        if group in groups:
            send_msg = "当前比赛站点列表：\n"
            for site in groups[group]:
                send_msg += site + "\n"
            await session.send(send_msg.strip())


@on_command("addsite")
async def add_site(session: CommandSession):
    global groups
    if session.event.detail_type == "group":
        group = session.event.group_id
        if group in groups:
            site = session.current_arg_text.strip()
            if not site:
                await session.send("空站点")
            elif site in groups[group]:
                await session.send("此站点已经在列表中")
            else:
                groups[group].add(site)
                await update_all_list()
                await session.send("添加站点成功")
        else:
            await session.send("当前群未激活，请联系QQ1023964019")


@on_command("delsite")
async def del_site(session: CommandSession):
    global groups
    if session.event.detail_type == "group":
        group = session.event.group_id
        if group in groups:
            site = session.current_arg_text.strip()
            if not site:
                await session.send("空站点")
            elif site not in groups[group]:
                await session.send("此站点未在列表中")
            else:
                groups[group].remove(site)
                await update_all_list()
                await session.send("删除站点成功")
        else:
            await session.send("当前群未激活，请联系QQ1023964019")


@on_command('askc')
async def ask_contests(session: CommandSession):
    global groups
    global cache_contests
    hours = session.current_arg_text.strip()
    if not hours or not hours.isdigit():
        hours = "48"
    hours = int(hours)
    if hours > 1000:
        hours = 1000
    if session.event.detail_type == "group" and session.event.group_id in groups:
        sites = groups[session.event.group_id]
    else:
        sites = DEFALUT_SITES
    site_filter = SiteFilter(sites)
    contests = await site_filter(cache_contests)
    time_filter = TimeFilter(hours * 60 * 60)
    contests = await time_filter(contests)
    if len(contests) > 0:
        send_msg = "比赛小助手提醒您，{}小时内的比赛有：\n".format(
            hours) + await contests_to_str(contests)
    else:
        send_msg = "比赛小助手提醒您，{}小时内没有比赛".format(hours)
    await session.send(send_msg)


@nonebot.scheduler.scheduled_job('cron', hour='23', minute='4')
async def daily():
    global groups
    global cache_contests
    bot = nonebot.get_bot()
    # now = datetime.now(pytz.timezone('Asia/Shanghai'))
    try:
        await update_cache()
        for group, sites in groups.items():
            site_filter = SiteFilter(sites)
            contests = await site_filter(cache_contests)
            time_filter = TimeFilter(60*60*24*2)
            contests = await time_filter(contests)
            if len(contests) > 0:
                send_msg = "比赛小助手提醒您，两天内的比赛有：\n" + await contests_to_str(contests)
                await bot.send_group_msg(group_id=group, message=send_msg)
    except CQHttpError:
        pass


@nonebot.scheduler.scheduled_job('interval', minutes=5)
async def last_hour():
    global groups
    global cache_contests
    global last_time
    bot = nonebot.get_bot()
    now = datetime.utcnow()
    try:
        for group, sites in groups.items():
            if last_time[group] and last_time[group] + timedelta(minutes=30) >= now:
                continue
            site_filter = SiteFilter(sites)
            contests = await site_filter(cache_contests)
            time_filter = TimeFilter(60*60)
            contests = await time_filter(contests)
            if len(contests) > 0:
                last_time[group] = now
                send_msg = "比赛小助手提醒您，一小时内的比赛有：\n" + await contests_to_str(contests)
                await bot.send_group_msg(group_id=group, message=send_msg)
    except CQHttpError:
        pass


async def contests_to_str(contests):
    msg = ""
    for contest in contests:
        start_time = datetime.strptime(
            contest["start"], '%Y-%m-%dT%H:%M:%S')
        utc_dt = start_time.replace(tzinfo=timezone.utc)
        bj_dt = utc_dt.astimezone(
            timezone(timedelta(hours=8)))
        bj_dt = bj_dt.replace(tzinfo=None).replace(microsecond=0)

        duration = timedelta(seconds=contest["duration"])
        msg += contest['event'] + ' ' + str(bj_dt)[:-3] + ' ' + str(duration)[
            :-3] + ' ' + contest['href'] + '\n'
    return msg.strip()


async def get_list(params, filters, limit=300):
    params['username'] = 'chitanda'
    params['api_key'] = '667bc0eec3f8b3f88569639ac554cd82b7f9672f'
    params['limit'] = limit
    params['order_by'] = 'start'
    nowtime = datetime.utcnow().replace(microsecond=0)
    params['start__gte'] = nowtime.isoformat()
    offset = 0
    contests = []

    times = 0
    while times < 10 and len(contests) < limit:
        x = requests.get(
            'https://clist.by:443/api/v1/contest', params=params)
        if x.status_code != 200:
            times += 1
            time.sleep(10)
            continue

        tmp_contests = x.json()['objects']
        for a_filter in filters:
            tmp_contests = await a_filter(tmp_contests)
        contests += tmp_contests
        if x.json()['meta']['next'] == None:
            break
        offset += 100
        params['offset'] = offset

    if times == 10:
        return 'fail', contests
    return 'success', contests


async def update_cache():
    global all_list
    global cache_contests
    check, cache_contests = await get_list(
        {}, [SiteFilter(all_list), DurationFilter(5*60*60)])
    if check == "fail":
        print('请求clist.by失败')


async def update_all_list(must=0):
    global all_list
    all_list_backup = all_list.copy()
    all_list = DEFALUT_SITES.copy()
    for sites in groups.values():
        all_list.update(sites)
    if must or (all_list_backup != all_list and not all_list.issubset(all_list_backup)):
        await update_cache()


class DurationFilter:
    def __init__(self, duration):
        # 比赛时间最长多少秒
        self.duration = duration

    async def __call__(self, contests):
        new_contests = []
        for contest in contests:
            if contest["duration"] <= self.duration:
                new_contests.append(contest)
        return new_contests


class SiteFilter:
    def __init__(self, sites):
        self.sites = sites

    async def __call__(self, contests):
        new_contests = []
        for contest in contests:
            occur = False
            for site in self.sites:
                if site in contest['href']:
                    occur = True
                    break
            if occur:
                new_contests.append(contest)
        return new_contests


class TimeFilter:
    def __init__(self, delta_time):
        # delta_time 为调用时当前时间+delta_time秒内开始的比赛
        self.delta_time = delta_time

    async def __call__(self, contests):
        now_time = datetime.utcnow()
        limit_time = now_time + timedelta(seconds=self.delta_time)
        new_contests = []
        for contest in contests:
            start_time = datetime.strptime(
                contest["start"], '%Y-%m-%dT%H:%M:%S')
            if start_time <= limit_time and start_time >= now_time:
                new_contests.append(contest)
        return new_contests
