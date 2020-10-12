import os
import discord
import dotenv
import json
import requests
import re
import time
import html
import asyncio
from bs4 import BeautifulSoup
import math
from db.db import JOMDdb
import random

from discord.ext import commands

dotenv.load_dotenv()

BOT_TOKEN=os.environ["JOMD_BOT_TOKEN"]
API_TOKEN=os.environ["JOMD_TOKEN"]

pref='+'
bot=commands.Bot(command_prefix=pref)


# Gets id, username, points, problem count and other basic details of user and returns a dict
def get_user(username):
    api_json = None
    try:
        api_response = requests.get(f'https://dmoj.ca/api/v2/user/{username}')
        api_json = json.loads(api_response.text)
    except:
        pass
    return api_json


# Returns pfp of dmoj user
def get_pfp(username):
    pfp = None
    try:
        response = requests.get(f'https://dmoj.ca/user/{username}')
        soup = BeautifulSoup(response.text,features="html5lib")
        pfp = soup.find('div',class_='user-gravatar').find('img')['src']
    except:
        pass
    return pfp

# Get placement/rank by points
def get_placement(username):
    rank = None
    try:
        response = requests.get(f'https://dmoj.ca/user/{username}')
        soup = BeautifulSoup(response.text,features="html5lib")
        rank_str = soup.find('div',class_='user-sidebar').findChildren(recursive=False)[3].text
        rank = int(rank_str.split('#')[-1])
    except:
        pass
    return rank

# Returns basic problem info
def get_problem(problem_code):
    problem_json = None
    try:
        response = requests.get(f'https://dmoj.ca/api/v2/problem/{problem_code}')
        problem_json = json.loads(response.text)
    except:
        pass
    return problem_json

# Lists of problems which fit conditions
def get_problems(page=1):
    problem_json = None
    try:
        response = requests.get(f'https://dmoj.ca/api/v2/problems?page={page}')
        problem_json = json.loads(response.text)
    except:
        pass
    return problem_json

# Returns submissions of user of a page
def get_submissions_page(username,page):
    submission_json = None
    try:
        response = requests.get(f'https://dmoj.ca/api/v2/submissions?user={username}&page={page}')
        submission_json = json.loads(response.text)
    except:
        pass
    return submission_json

# Get all submissions
async def get_submissions(username):
    #TODO: Refactor code and make a seperate method for db stuff

    sub_json = get_submissions_page(username,1)
    pages = sub_json['data']['total_pages']
    total_submissions = sub_json['data']['total_objects']
    db = JOMDdb()
    cached_submissions = db.get_submissions(username)
    submissions_to_query = total_submissions-len(cached_submissions)
    pages_to_query = math.ceil(submissions_to_query/1000)
    future = [None]*max(pages_to_query,1)
    submission_page = [None]*max(pages_to_query,1)

    submission_page[0] = sub_json

    loop = asyncio.get_event_loop()
    for i in range(1,pages_to_query):
        future[i] = loop.run_in_executor(None, get_submissions_page, username, i+1)
    for i in range(1,pages_to_query):
        submission_page[i]=await future[i]
    submissions = []
    for submission in submission_page:
        submissions += submission['data']['objects']
    db.cache_submission(submissions)
    return submissions[:submissions_to_query]+cached_submissions

# Calculate points based on submissions
def calculate_points(points,fully_solved):
    b = 150*(1-0.997**fully_solved)
    p = 0
    for i in range(min(100,len(points))):
        p += (0.95**i)*points[i]
    return b+p

# Returns latest submissions on user 
def get_latest_submission(username,num):

    def parse_submission(soup):
        submission_id = soup['id']
        result = soup.find(class_='sub-result')['class'][-1]
        score = soup.find(class_='sub-result').find(class_='score').text.split('/')
        score_num,score_denom = list(map(int,score))
        lang = soup.find(class_='language').text
        problem_code = soup.find(class_='name').find('a')['href'].split('/')[-1]
        name = soup.find(class_='name').find('a').text
        date = soup.find(class_='time-with-rel')['title']
        try:
            time = float(soup.find('div',class_='time')['title'][:-1])  # removes the s
        except:
            time = None
        memory = soup.find('div',class_='memory').text

        problem = get_problem(problem_code)
        return {
            "id":submission_id,
            "result":result,
            "score_num":score_num,
            "score_denom":score_denom,
            "points":score_num/score_denom,
            "language":lang,
            "problem_code":problem_code,
            "problem_name":name,
            "date":date,
            "time":time,
            "memory":memory,
        }


    matches = None
    try:
        response = requests.get(f'https://dmoj.ca/submissions/user/{username}/')
        soup = BeautifulSoup(response.text,features="html5lib")
        matches = list(map(parse_submission,soup.find_all('div',class_='submission-row')))
    except:
        pass
    return matches[:num]

def cache_problems():
    pass

# Get single submission perhaps not valid 
# Must pass in session cookie
def get_submission(submission_id):
    submission_json = None
    try:
        response = requests.get(f'https://dmoj.ca/api/v2/submission/{submission_id}')
        submission_json = json.loads(response.text)
    except:
        pass
    return submission_json
    
def get_problem_type(id):
    options = None
    try:
        response = requests.get(f'https://dmoj.ca/problems/?show_types=1')
        soup = BeautifulSoup(response.text,features="html5lib")
        options = soup.find('select',id=id).find_all('option')
        options = [option.text.strip() for option in options if option['value'].isdigit()]
    except:
        pass
    return options

def is_int(arg):
    try:
        int(arg)
        return True
    except:
        return False


@bot.command(name='user')
async def user(ctx,*args):
    # Beautify the errors
    if len(args) > 2:
        return await ctx.send(f'Too many arguments, {pref}user <user> <latest submissions>')
    
    if len(args) < 1:
        return await ctx.send(f'Too few arguments, {pref}user <user> <latest submissions>')

    if len(args) == 2:
        if not is_int(args[1]):
            return await ctx.send(f'{args[1]} is not an integer')

        if int(args[1]) > 8 :
            return await ctx.send(f'Requesting too many submissions, Max (8)')

        if int(args[1]) < 1 :
            return await ctx.send(f'Pls no troll :>')

    username=args[0]
    user = get_user(username)
    
    if "error" in user:
        return await ctx.send(f'{username} does not exist on DMOJ')
    
    data = user['data']['object']
    username = data['username']
    embed = discord.Embed(
                        title = username,
                        url = f'https://dmoj.ca/user/{username}',
                        description = 'Calculated points: %.2f' % data['performance_points'],
                        color=0xfcdb05,
    )

    is_rated = lambda user:0 if user['rating'] is None else 1

    embed.set_thumbnail(url=get_pfp(username))
    embed.add_field(name="Rank by points", value=get_placement(username), inline=False)
    embed.add_field(name="Problems Solved", value=data['problem_count'], inline=False)
    embed.add_field(name="Rating", value=data['rating'], inline=True)
    embed.add_field(name="Contests Written", value=sum(map(is_rated,data['contests'])), inline=True)
    await ctx.send(embed=embed)

    if len(args) == 1:
        return
    

    latest_subs = int(args[1])
    submissions = get_latest_submission(username,latest_subs)
    embed=discord.Embed(title=f"{username}'s latest submissions",color=0xfcdb05)
    
    for submission in submissions:
        embed.add_field(
            name="%d / %d" % (submission['score_num'],submission['score_denom']),
            value="%s | %s" % (submission['result'],submission['language']), 
            inline=True
        )
        embed.add_field(
            name="%s" % html.unescape(submission['problem_name']),
            value="%s | [Problem](https://dmoj.ca/problem/%s)" % (submission['date'],submission['problem_code']),
            inline=True
        )
        try:
            embed.add_field(name="%.2fs" % (submission['time']), value="%s" % submission['memory'], inline=True)
        except:
            embed.add_field(name="%s" % (time), value="%s" % submission['memory'], inline=True)

    await ctx.send(embed=embed)
    return None

@bot.command(name='predict')
async def predict(ctx,*args):

    if len(args) > 11:
        return await ctx.send(f'Too many arguments, {pref}predict <user> <points>')

    if len(args) < 2:
        return await ctx.send(f'Too few arguments, {pref}predict <user> <points>')

    if any(not is_int(points) for points in args[1:]):    # allow negative numbers cause why not
        return await ctx.send(f'Integer points only!')

    username = args[0]
    user = get_user(username)
    if "error" in user:
        return await ctx.send(f'{username} does not exist on DMOJ')
    
    username = user['data']['object']['username']
    msg = await ctx.send(f'Fetching Submissions for {username}. This may take a few seconds')

    subs = await get_submissions(username)
    
    problems = get_problems()['data']['objects']
    code_to_points = dict()
    problems_AC = dict()
    for i in subs:
        problem_code, points, result = i['problem'], i['points'], i['result']
        if points is not None and points != 0:

            if  result == 'AC' and problem_code not in problems_AC:
                problems_AC[problem_code]=1

            if problem_code not in code_to_points:
                code_to_points[problem_code]=points
            
            elif points>code_to_points[problem_code]:
                code_to_points[problem_code]=points

    fully_solved_problems=sum(list(problems_AC.values()))
    points = list(code_to_points.values())
    points.sort(reverse=True)
    embed = discord.Embed(
                    title=f'Point prediction for {username}', 
                    description='Current points: %.2fp' % calculate_points(points,fully_solved_problems), 
                    color=0xfcdb05
    )

    embed.set_thumbnail(url=get_pfp(username))

    for i in args[1:]:
        points.insert(len(points),int(i))
        fully_solved_problems+=1
        points.sort(reverse=True)
        updated_points=calculate_points(points,fully_solved_problems)
        embed.add_field(name="Solve another %sp" % i, value="Total points: %.2fp" % updated_points, inline=False)
    await msg.edit(content='',embed=embed)

@bot.command(name='cache')
async def cache(ctx,*args):

    if len(args) == 0:
        return await ctx.send(f'Usage: {pref}cache [username]')

    username = args[0]
    user = get_user(username)
    if "error" in user:
        return await ctx.send(f'{username} does not exist on DMOJ')
    
    username = user['data']['object']['username']
    await get_submissions(username)

    return await ctx.send(f'{username}\'s submissions have been cached.')

@bot.command(name='gimme')
async def gimmie(ctx,*args):
    if len(args) < 1:
        return await ctx.send(f'Usage: {pref}gimmie username [points] [type, comma seperated]')

    # category/types
    username=args[0]
    user = get_user(username)
    
    if "error" in user:
        return await ctx.send(f'{username} does not exist on DMOJ')
    
    data = user['data']['object']
    username = data['username']

    points = args[1] if len(args)>1 else None
    if points is None:
        point_low=1
        point_high=50
    elif '-' in points:    # range
        points = points.split('-')
        if len(points) != 2:
            return await ctx.send(f'Range requires two values seperated by a \'')
        if not is_int(points[0]) or not is_int(points[1]):
            return await ctx.send(f'Point ranges are not an integer')
        point_low, point_high = int(points[0]),int(points[1])
    elif points is not None:
        if not is_int(points):
            return await ctx.send(f'Point is not an integer')
        point_low = point_high = int(points)

    shorthands = {
        'adhoc':['Ad Hoc'],
        'math':['Advanced Math','Intermediate Math','Simple Math'],
        'bf':['Brute Force'],
        'ctf':['Capture the Flag'],
        'ds':['Data Structures'],
        'd&c':['Divide and Conquer'],
        'dp':['Dynamic Programming'],
        'geo':['Geometry'],
        'gt':['Graph Theory'],
        'greedy':['Greedy Algorithms'],
        'regex':['Regular Expressions'],
        'string':['String Algorithms'],
    }

    filters = None
    if len(args) > 2:
        filters = args[2].split(',')
        def parse_filter(filter):
            if filter in shorthands:
                return shorthands[filter]
            else:
                return [filter]
        
        filters_list = map(parse_filter,filters)
        filters = [filter for filters in filters_list for filter in filters]

    
    
    db = JOMDdb()
    problems = db.get_unsolvedproblems(username,point_low,point_high)

    results = []

    # TODO: Improve filtering to include group and type
    if filters is not None:
        for problem in problems:
            for filter in filters:
                if filter in problem['types']:
                    results.append(problem)
                    break
    else:
        results = problems

    if len(results)==0:
        return await ctx.send('No problems found which satify the condition')

    problem = random.choice(results)

    points = '%d' % problem['points']
    if problem['partial']:
        points += 'p'
        
    memory = problem['memory_limit']

    if memory >= 1024:
        memory = '%dM' % (memory//1024)
    else:
        memory = '%dK' % (memory)

    embed = discord.Embed(
                    title = problem['name'],
                    url = 'https://dmoj.ca/problem/%s' % problem['code'],
                    description = 'Points: %s\nProblem Types: %s' % (points,', '.join(problem['types'])),
                    color=0xfcdb05,
    )

    embed.set_thumbnail(url=get_pfp(username))
    embed.add_field(name='Group', value=problem['group'],inline=True)
    embed.add_field(name='Time', value='%ss' % problem['time_limit'],inline=True)
    embed.add_field(name='Memory', value=memory,inline=True)
    return await ctx.send(embed=embed)
    


# you will only see submission details if the user solved the problem
# @bot.event
# async def on_message(message):
#     if re.match(r'https://dmoj.ca/submission/(\d*)',message.content) is not None:
#         print(message.content)
#         submissions = re.findall(r'https://dmoj.ca/submission/(\d*)',message.content)
#         print(submissions)
#         for submission_id in submissions:
#             sub = get_submission(submission_id)
#             print(submission_id,sub)

        

def main():
    print("Bot is Running")
    bot.run(BOT_TOKEN)

if __name__ == "__main__":
    main()
