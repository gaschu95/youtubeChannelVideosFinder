#!/usr/bin/env python


# ------------------------------------------
# Imports
# ------------------------------------------
import urllib
import requests
import json
import time
import datetime
import sys
import argparse
import logging

from .rfc3339 import rfc3339

youtubeApiUrl = 'https://www.googleapis.com/youtube/v3/'
youtubeChannelsApiUrl = youtubeApiUrl + 'channels?key={0}&'
youtubeSearchApiUrl = youtubeApiUrl + 'search?key={0}&'

requestParametersChannelId = 'forUsername={0}&part=id'
requestChannelVideosInfo = 'channelId={0}&part=id&order=date&type=video&publishedBefore={1}&publishedAfter={2}&pageToken={3}&maxResults=50'

defaultInterval = datetime.timedelta(weeks=52)
defaultTimeToGoBackTo = datetime.datetime.strptime('2005-02-14','%Y-%m-%d') #Youtube was founded => there are no earlier videos

# logger configuration
log = logging.getLogger('_name_')
logFormat = '[%(asctime)s] [%(levelname)s] - %(message)s'
# format ref: https://docs.python.org/2/library/logging.html#logrecord-attributes

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(logFormat))
log.addHandler(handler)

# ------------------------------------------
# Functions
# ------------------------------------------

def read_args():
	'''
	read args from stdin and returns them
	'''
		
	# we first initialize our parser then we use it to parse the provided args
	# 	references: 
	# 		https://docs.python.org/2/library/argparse.html
	#		http://pymotw.com/2/argparse/
	#		https://docs.python.org/2/howto/argparse.html

	parser = argparse.ArgumentParser(description='This program finds all videos in a given Youtube channel')

	parser.add_argument('-k', '--api-key', dest='apiKey', action='store', required=True, help='Google Data API key to use. You can get one here: https://console.developers.google.com')
	parser.add_argument('-c', '--channel', dest='channel', action='store', required=True, help='Youtube channel to get videos from')

	parser.add_argument('-x', '--latest-date', dest='latest', action='store', help='Videos published after this date will not be retrieved (expected format: yyyy-mm-dd). If not specified, the current date is taken')
	parser.add_argument('-y', '--earliest-date', dest='earliest', action='store', help='Videos published before this date will not be retrieved (expected format: yyyy-mm-dd). If not specified, we go back one month (related to -b / --date-from)')
	parser.add_argument('-i', '--interval', dest='interval', action='store', help='Longest period of time (in days) to retrieve videos at a time for. Since the Youtube API only permits to retrieve 500 results, the interval cannot be too big, otherwise we might hit the limit. Default: 52')

	outputDetailLevel = parser.add_mutually_exclusive_group()
	outputDetailLevel.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=False, help='Only print out results.. or fatal errors')
	outputDetailLevel.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False, help='Print out detailed information during execution (e.g., invoked URLs, ...)')
	outputDetailLevel.add_argument('-d', '--debug', dest='debug', action='store_true', default=False, help='Print out all the gory details')

	parser.add_argument('--version', action='version', version='1.0') # aka how much time can we lose while programming :p (https://code.google.com/p/argparse/issues/detail?id=43)

	args = parser.parse_args()

	if args.verbose:
		log.setLevel(level=logging.INFO)
	elif args.debug:
		log.setLevel(level=logging.DEBUG)
	elif args.quiet:
		log.setLevel(level=logging.ERROR)
	else:
		log.setLevel(level=logging.WARN)
	return args

def get_channel_id(apiKey, channelName):
	'''
	Returns the ChannelID for the specified ChannelName
	'''
	log.info('Searching channel id for channel: %s',channelName)
	channelId = -1
	try:
		url = youtubeChannelsApiUrl.format(apiKey) + requestParametersChannelId.format(channelName)
		log.debug("Request: %s",url)
		
		log.debug('Sending request')
		response = requests.get(url)
		
		log.debug('Parsing the response')
		responseAsJson = json.loads(response.content.decode('utf-8'))

		response.close()
		
		log.debug('Response: %s',json.dumps(responseAsJson,indent=4))
		
		log.debug('Extracting the channel id')
		if(responseAsJson['pageInfo'].get('totalResults') > 0):
			returnedInfo = responseAsJson['items'][0]
			channelId = returnedInfo.get('id')
			log.info('Channel id found: %s',str(channelId))
		else:
			log.debug('Response received but it contains no item')
			raise Exception('The channel id could not be retrieved. Make sure that the channel name is correct')
			
		if(responseAsJson['pageInfo'].get('totalResults') > 1):
			log.debug('Multiple channels were received in the response. If this happens, something can probably be improved around here')
	except Exception:
		log.error('An exception occurred while trying to retrieve the channel id',exc_info=True)
	
	return channelId

def _get_channel_videos_published_in_interval(apiKey,channelId,publishedBefore,publishedAfter):
	'''
	!!! PLEASE USE get_channel_videos() !!!
	Returns a list of videoIDs that were published by the specified channel between publishedAfter and publishedBefore
	'''
	log.info('Getting videos published before %s and after %s',publishedBefore,publishedAfter)
	videoList = []
	foundAll = False
	
	nextPageToken = ''

	while not foundAll:
		try:
			url = youtubeSearchApiUrl.format(apiKey) + requestChannelVideosInfo.format(channelId,publishedBefore,publishedAfter,nextPageToken)
			log.debug('Request: %s',url)
			
			log.debug('Sending request')
			response = requests.get(url)
			
			log.debug('Parsing the response')
			responseAsJson = json.loads(response.content.decode('utf-8'))
			
			response.close()
			
			returnedVideos = responseAsJson['items']
			log.debug('Response: %s',json.dumps(returnedVideos,indent=4))
			
			for video in returnedVideos:
				videoList.append(video.get('id').get('videoId')) 
				
			try:
				nextPageToken = responseAsJson['nextPageToken']
				log.info('More videos to load, continuing')
			except Exception:
				log.info('No more videos to load')
				foundAll = True
		except Exception:
			log.error('An exception occurred while trying to retrieve a subset of the channel videos. Stopping search.',exc_info=True)
			foundAll = True		
	
	log.info('Found %d video(s) in this time interval',len(videoList))
	return videoList	
	
def get_channel_videos(apiKey, channelId, earliest=None, latest=None, timeInterval=None):
	'''
	Returns a list of video IDs that were published between latest and earliest
	'''
	# convert to datetime objects if strings
	if isinstance(earliest, str): earliest = datetime.datetime.strptime(earliest,'%Y-%m-%d')
	if isinstance(latest, str): latest = datetime.datetime.strptime(latest,'%Y-%m-%d')
	if isinstance(timeInterval, str): timeInterval = datetime.timedelta(days=int(timeInterval))
	elif isinstance(timeInterval, int): timeInterval = datetime.timedelta(days=timeInterval)

	# use default values if None
	if latest is None: latest = datetime.datetime.now()
	if earliest is None: earliest = defaultTimeToGoBackTo
	if timeInterval is None: timeInterval = defaultInterval

	log.info('Searching for videos published in channel between %s and %s',latest,earliest)
	if(latest < earliest):
		raise Exception('The date to start from cannot be before the date to go back to!')
	
	videoList = []
	
	# initialization
	latererer = latest
	earliererer = latererer - timeInterval
	
	done = False
	
	while not done:
		if(earliererer < earliest):
			log.debug('The interval is now larger than the remaining time span to retrieve videos for. Using the date to go back to as next boundary')
			earliererer = earliest
		
		if(earliererer == earliest):
			log.debug('Last round-trip')
			done = True
		
		log.debug('Converting timestamps to RFC3339 format')
		earliererer_rfc3339 = rfc3339(earliererer,utc=True)
		latererer_rfc3339 = rfc3339(latererer,utc=True)
		
		videosPublishedInInterval = _get_channel_videos_published_in_interval(apiKey,channelId,latererer_rfc3339,earliererer_rfc3339)
		
		log.debug('Adding videos found in the interval to the results list')
		videoList.extend(videosPublishedInInterval)
		log.debug('Total video(s) found so far: %d',len(videoList))
		
		if(not done):
			# we simply continue from where we are
			latererer = earliererer
			
			# calculate the next date to go back to based on the given interval
			nextDate = earliererer - timeInterval
			log.debug('Calculating the next date to go back to based on the interval: %s - %s => %s',earliererer,timeInterval,nextDate)
			earliererer = nextDate
			
	log.info('Found %d video(s) in total',len(videoList))
	return videoList	


# ------------------------------------------
# Entry point
# ------------------------------------------
def main():
	args = read_args()
	try:
		channelId = get_channel_id(args.apiKey, args.channel)
		if(channelId == -1):
			raise Exception('Impossible to continue without the channel id')
		
		channelVideos = get_channel_videos(args.apiKey, channelId, args.earliest, args.latest, args.interval)
		
		if(len(channelVideos) <= 0):
			log.info("No video found for that channel! Either there's none or a problem occurred. Enable verbose or debug logging for more details..")
			sys.exit(0)
		
		for video in channelVideos:
			print(video)
		log.info('Done!')
	except Exception:
		log.critical('We tried our best but still..',exc_info=True)
		sys.exit(2)

if __name__ == '__main__':
    main()