
import os
import sys
from twitchio.ext import commands

import json
import http.client as http
import re
from datetime import datetime



queue = []
playlistCount = 0
history = []



bot = commands.Bot(
    # set up the bot
    irc_token=os.environ['TMI_TOKEN'],
    client_id=os.environ['CLIENT_ID'],
    nick=os.environ['BOT_NICK'],
    prefix=os.environ['BOT_PREFIX'],
    initial_channels=[os.environ['CHANNEL']]
)

@bot.event
async def event_ready():
    print(f"{os.environ['BOT_NICK']} is online!")
    ws = bot._ws  # this is only needed to send messages within event_ready
    await ws.send_privmsg(os.environ['CHANNEL'], f"/me has landed! Now handling beat saber song requests.")


@bot.event
async def event_message(ctx):
    # make sure the bot ignores itself
    if ctx.author.name.lower() == os.environ['BOT_NICK'].lower():
        return

    await bot.handle_commands(ctx)

    sys.stdout.flush()
    sys.stderr.flush()


@bot.command(name="help")
async def help(ctx):
    #TODO: Implement help menu
    args = ctx.content.split(" ")
    if len(args) == 1:
        await ctx.send('Commands: !ping, !bsr, !oops, !queue, !history, !ss. Type !help <command> for more info on individual commands')
        return

    if args[1].lower() == "ping":
        await ctx.send("Lets you know the bot is still alive")
        return
    elif args[1].lower() == "bsr":
        await ctx.send("Adds the given beatsaver.com key to the queue. Syntax: !bsr <key>")
        return
    elif args[1].lower() == "ss":
        await ctx.send("Displays %s's scoresaber information." % os.environ['CHANNEL'])
        return
    elif args[1].lower() == "oops":
        await ctx.send("Removes your previously requested song from the queue.")
        return
    elif args[1].lower() == "queue":
        await ctx.send("Displays the songs currently in queue")
        return
    elif args[1].lower() == "history":
        await ctx.send("Displays the songs that have previously been requested during this stream.")
        return
    else:
        await ctx.send("Error: Unrecognized command %s!" % args[1])

@bot.command(name="ping")
async def ping(ctx):
    print("\nPinged by %s." % ctx.author.name)
    await ctx.send('Pong!')


@bot.command(name="ss")
async def scoreSaberLookup(ctx):
    print("\nLooking up scoresaber info. SS requested by %s." % ctx.author.name)

    conn = http.HTTPSConnection("new.scoresaber.com")
    if not conn:
        await ctx.send("Could not establish a connection with scoresaber.com!")
        return

    conn.request("GET", "/api/player/%s/full" % os.environ['SCORESABER_ID'])
    res = conn.getresponse()

    if res.status != 200:
        print("ERROR: Failed to request profile data! response:", res.status)
        await ctx.send("Error: Unable to fetch scoresaber data!")
    else:
        data = json.loads(res.read())
        fmstr = "! %s: Global Ranking #%d, %d pp, %.2f%% average ranked accuracy, %d total plays, %d ranked plays. Link: https://new.scoresaber.com/u/%s"
        r =  fmstr % (data["playerInfo"]["name"], data["playerInfo"]["rank"], data["playerInfo"]["pp"], data["scoreStats"]["averageRankedAccuracy"], data["scoreStats"]["totalPlayCount"], data["scoreStats"]["rankedPlayCount"], os.environ['SCORESABER_ID'])
        await ctx.send(r)#split this up in an attempt to keep the line length down. Clearly that failed though

    conn.close()
    print("Success")

#Note: I've made the explicit decision not to implement song requests by song name because more often than not
#   the requests that are made with that method end up being bad.
@bot.command(name="bsr")
async def beatSaberRequest(ctx):
    global queue

    args = ctx.content.split(" ")
    if len(args) != 2:
        await ctx.send("Usage: !bsr <song key> where <song key> is a song key from beatsaver.com.")
        return

    if not re.fullmatch("[0-9a-fA-F]+", args[1]):
        print("\nReceived bad request from %s." % ctx.author.name)
        await ctx.send("Invalid Key Provided")
        return

    if any(args[1] == s['key'] for s in queue) or any(args[1] == s['key'] for s in history):
        print("\nReceived duplicate request from %s for key %s." % (ctx.author.name, args[1]))
        await ctx.send("Key %s already exists in queue or history." % args[1])
        return


    print("\nLooking up key %s." % args[1])

    serv = "beatsaver.com"
    ep = "/api/maps/detail/%s"

    conn = http.HTTPSConnection(serv)
    if not conn:
        print("Error: Failed to establish connection with beatsaver.com!")
        await ctx.send("Could not establish a connection with beatsaver.com!")
        return

    #These being seperate calls really caused me a lot of pain -_-
    conn.request("GET", ep % args[1], headers={'User-Agent': 'TwitchQuestIntegrationBot/0.0.0'})
    detailsRes = conn.getresponse()

    #print("Accessing:", "https://" + serv + ep % args[1])

    if not detailsRes:
        print("Error: Could not complete request with beatsaver.com!")
        await ctx.send("Could not complete request!")
        conn.close()
        return

    if detailsRes.status != 200 and detailsRes.status != 304:
        if detailsRes.status == 404:
            print("Song not found!")
            await ctx.send("Error: song for key %s not found!" % args[1])
        else:
            print("Error: Received unexpected response from beatsaver.com! (%d)" % detailsRes.status)
            await ctx.send("Error: Unable to access beatsaver.com!")

        conn.close()
        return

    details = json.loads(detailsRes.read())
    if details['stats']['rating'] < float(os.environ['MIN_SONG_APPROVAL']):
        print("%s requested a crap song. Rating: %d" % (ctx.author.name, details['stats']['rating']))
        await ctx.send("Request for song \"%s\" by %s denied. Map must have a rating of at least %s." % (details['name'], details['metadata']['levelAuthorName'], os.environ['MIN_SONG_APPROVAL']))
        return

    item = {
        'key': args[1],
        'hash':details['hash'],
        "songName":details['metadata']['songName'],
        'requester':ctx.author.name
    }
    queue.append(item)

    conn.close()

    print("Song %s successfully added to queue." % item['songName'])
    await ctx.send("Added %s[%s] (%.1f%%) Requested by %s. Queue currently contains %d songs." % (details['name'], details['metadata']['levelAuthorName'], details['stats']['rating'], ctx.author.name, len(queue)))

@bot.command(name="oops")
async def removeLastReq(ctx):
    global queue

    if len(queue) == 0:
        await ctx.send("No songs in queue to.")
        return

    for i in range(len(queue) - 1, -1, -1):
        if queue[i]['requester'] == ctx.author.name:
            del queue[i]
            break

    await ctx.send("No songs requested by %s found." % ctx.author.name)

@bot.command(name="genBplist")
async def genPlaylist(ctx):
    global queue
    global history
    global playlistCount

    if ctx.author.name.lower() != os.environ['CHANNEL'].lower():
        return

    if len(queue) == 0:
        await ctx.send("Cannot generate playlist: Queue is empty.")
        return

    await ctx.send("Generating Playlist.")

    #Playlist name: Queue #{number generated during stream} for {datetime}
    playlistCount += 1

    bplist = {}

    dt = datetime.now()
    bplist["playlistTitle"] = "Queue #%d from %s" % (playlistCount, dt.date())
    bplist['playlistAuthor'] = os.environ['BOT_NICK']

    await ctx.send("Adding thumbnail.")
    f = open(os.environ['PLAYLIST_THUMBNAIL'], "r")
    bplist['image'] = "data:image/png;base64," + f.read()
    f.close()

    await ctx.send("Adding songs.")
    bplist["songs"] = queue

    await ctx.send("Exporting data.")
    rawData = json.dumps(bplist)
    fileName = "queue-%d_%s.bplist" % (playlistCount, dt.date())
    f = open(os.environ['OUTPUT_FOLDER'] + fileName, "w")
    f.write(rawData)
    f.close()

    history.extend(queue)
    queue = []

    await ctx.send("Playlist %s has been generated!" % fileName)

@bot.command(name="queue")
async def showQueue(ctx):
    global queue

    if len(queue) == 0:
        await ctx.send("Queue is empty!")
        return

    output = "Songs"

    for req in queue:
        output += ", %s (%s)" % (req['songName'], req['key'])

    await ctx.send(output)

@bot.command(name="history")
async def showHistory(ctx):
    global history

    if len(history) == 0:
        await ctx.send("History is empty!")
        return
    output = "Played Songs"

    for req in history:
        output += ", %s (%s)" % (req['songName'], req['key'])

    await ctx.send(output)

if __name__ == "__main__":
    bot.run()
