#!/usr/bin/python

import json

import MySQLdb

from db import Database
# Substitute user/pass info in connect() as necessary
conn = MySQLdb.connect(db='PlacePulse',user='root',passwd='12345678')
cur = conn.cursor()

# DB data
cities = dict()
locations = dict()
studyidsD={}
placeids = []
studyids=[]
cityidset=set()
studyidset=set()

out_studies = open('studies_dump.json','w')
out_votes = open('votes_dump.json','w')
out_locations = open('locations_dump.json','w')

# Function ganked from python-iptools: http://code.google.com/p/python-iptools/
def long2ip (l):
    _MAX_IP = 0xffffffff
    _MIN_IP = 0x0
    if _MAX_IP < l or l < 0:
        raise TypeError("expected int between 0 and %d inclusive" % _MAX_IP)
    return '%d.%d.%d.%d' % (l>>24 & 255, l>>16 & 255, l>>8 & 255, l & 255) 

def SHA1(d):
    import hashlib
    h = hashlib.new('sha1')
    h.update(str(d))
    return h.hexdigest()

def for_result(func,results):
    res = results.fetch_row()
    while res != ():
        func(res)
        res = results.fetch_row()

def rip_cities():
    conn.query("SELECT * FROM city")
    res = conn.store_result()
    
    def city_to_place(city_row):
        # city tuple is (id, city name, country)
        #cities[city_row[0][0]] = "%s, %s" % (city_row[0][1],city_row[0][2])
	placeid = Database.places.insert({'name':city_row[0][1],
			'data_resolution':1000,
			'location_distribution':'randomly'})
	cities[city_row[0][0]] = placeid
    	placeids.append(placeid)
    for_result(city_to_place,res)


def rip_studies():
    conn.query("SELECT * FROM questions")
    res = conn.store_result()
    
    def save_study(study_row):
        # questions row is (id,question,id_study)
        # we're throwing id_study away, and replacing it with a mongo _id
        # which is SHA1('study_' + id)
	studyid = Database.studies.insert({
					'study_question': study_row[0][1],
					'study_public': True,
					'study_name':study_row[0][1],
					'places_id':placeids})
	studyids.append(study_row[0][0])
	#print(study_row[0][0])
	studyidsD[study_row[0][0]]=studyid
	'''
        out_studies.write(json.dumps({
            '_id': SHA1('study_' + str(study_row[0][0])),
            'question': study_row[0][1]
        }))
        out_studies.write('\n')
	'''
    
    for_result(save_study,res)
    out_studies.close()

highestLocIdx = 0

def rip_locations_and_places():
    # FIXME: ugh.
    global highestLocIdx
    # first, load all locations into a dict
    locations = dict()
    conn.query("SELECT * FROM locations")
    res = conn.store_result()
    
    
    
    def save_location(loc_row):
        # FIXME: ughhhh
        global highestLocIdx
        # locations row is (id,lat,lng,lastUpdated)
        locations[int(loc_row[0][0])] = {
            'lat': float(loc_row[0][1]),
            'lng': float(loc_row[0][2]),
            'places': []
        }
        highestLocIdx = max(highestLocIdx,loc_row[0][0])
    for_result(save_location,res)
    
    # now, correlate places table with locations
    conn.query("SELECT * FROM places")
    res = conn.store_result()
    
    def save_place(place_row):
        # FIXME: ughhhhhhhhhhh
        global highestLocIdx
        # places row is (id, id_city, lat, lng, _, _, _, heading, pitch, mutant, id_location, total_votes)
        place_row = place_row[0]
        place = {
            'sql_id': int(place_row[0]),
            'city': cities.get(int(place_row[1]),'<UNKNOWN CITY>'),
            'heading': place_row[7],
            'pitch': place_row[8],
            'num_votes': place_row[11]
        }
	#reference 
	'''
    Database.locations.insert({
        'loc': [request.form['lat'],request.form['lng']],
        'study_id': request.form['study_id'],
        'heading': 0,
        'pitch': 0,
        'bucket' : Buckets.Unknown,
        'votes' : 0
    })
	'''
	#print(place_row[1])
	if(place_row[1] not in cityidset):
		cityidset.add(place_row[1])
		placeid = Database.places.insert({'name':place_row[1],
			'data_resolution':1000,
			'location_distribution':'randomly'})
		cities[place_row[1]] = placeid
    		placeids.append(placeid)
		
	if(place_row[1] in ['1','2','3','4','5']):
		Database.locations.insert({'loc':[float(place_row[2]),float(place_row[3])],
					'heading':place_row[7],
					'pitch':place_row[8],
					'type':'gsv',
					'places_id':[cities[place_row[1]]]})
	
        # if mutant, add file_location
        if place_row[9]:
            place['mutant'] = True
            place['file_location_400_300'] = place_row[4]
            place['file_location'] = place_row[5]
        location = locations.get(place_row[10])
        if location:
            if location['lat'] != place_row[2] or location['lng'] != place_row[3]:
                # print "ERROR: place #%s and location #%s don't have matching latlng!" % (place_row[0],place_row[10])
                place['lat'] = float(place_row[2])
                place['lng'] = float(place_row[3])
            location['places'].append(place)
        else:
            # print "ERROR: location doesn't exist for place #%s" % place_row[0]
            # Create a location after the fact
            highestLocIdx += 1
            locations[highestLocIdx] = {
                'lat': float(place_row[2]),
                'lng': float(place_row[3]),
                'places': [place]
            }

    for_result(save_place,res)
    
'''
    for locKey in locations.keys():
        out_locations.write(json.dumps(locations[locKey]))
        out_locations.write('\n')
'''
    #out_locations.close()
    
def rip_votes():
    conn.query("SELECT * FROM votes")
    
    res = conn.store_result()

    def save_vote(vote_row):
        from time import mktime
        vote_row = vote_row[0]
               
        # vote_row is (id,id_question,id_left,id_left_city,id_right,id_right_city,winner,uuid_pulse,ip_address,timestamp)
        vote = {
            'study': SHA1('study_' + str(vote_row[1])),
            'left_sql_id': int(vote_row[2]),
            'right_sql_id': int(vote_row[4]),
            'left_city': cities.get(vote_row[3],"<UNKNOWN CITY>"),
            'right_city': cities.get(vote_row[5],"<UNKNOWN CITY>"),
            'winner_sql_id': int(vote_row[6]),
            'uuid_pulse': vote_row[7],
            'ip_address': long2ip(long(vote_row[8])),
            'timestamp': {
                '$date': int(mktime(vote_row[9].timetuple()))*1000
            }
        }
	'''
    Database.votes.insert({
        'study_id' : request.form['study_id'],
        'left' : request.form['left'],
        'right' : request.form['right'],
        'choice' : request.form['choice'],
        'timestamp': datetime.now()
    })
	'''
	if(vote_row[1]!=0):
		Database.votes.insert({'study_id':studyidsD[vote_row[1]],
				'left': int(vote_row[2]),
				'right': int(vote_row[4]),
				'left_city':cities[vote_row[3]] if vote_row[3] else None,
				'right_city':cities[vote_row[5]] if vote_row[3] else None,
				'choice':int(vote_row[6]),
				'timestamp': {
					'date': int(mktime(vote_row[9].timetuple()))*1000
				}})
        #out_votes.write(json.dumps(vote))
        #out_votes.write('\n')
    for_result(save_vote,res)
    out_votes.close()

rip_cities()
#switched order of locations and studies because unknown cities are added in during the locations_and_places()
rip_locations_and_places()
rip_studies()
rip_votes()