from flask import Module

from flask import redirect,render_template,request,session,url_for

from util import *

from datetime import datetime
from random import random,randint
from uuid import uuid4


study = Module(__name__)

from db import Database

#--------------------Create
@study.route("/study/create/")
def serve_create_study():
    if getLoggedInUser() is None:
        return redirect(url_for('login.signin',next="/study/create"))
    return auto_template('study_create.html')
    
@study.route('/study/create/',methods=['POST'])
def create_study():    
    #Insert new Place
    newPlaceID = Database.places.insert({
    'data_resolution': request.form['data_resolution'],
    'location_distribution': request.form['location_distribution'],
    'polygon': request.form['polygon'],
    'place_name': request.form['place_name'],
    'owner': session['userObj']['email'],
    })
    
    # Insert the new study into Mongo
    newStudyID = Database.studies.insert({
        'study_name': request.form['study_name'],
        'study_question': request.form['study_question'],
        'study_public': request.form['study_public'],
        'places_id': [newPlaceID],
        'owner': session['userObj']['email'],
        })
    session['currentStudy'] = newStudyID
    # Return the ID for the client to rendezvous at /study/populate/<id>
    return jsonifyResponse({
        'studyID': str(newStudyID),
        'placeID': str(newPlaceID)
    })

#--------------------Populate
@study.route('/place/populate/<place_id>/',methods=['GET'])
def serve_populate_place(place_id):
    place = Database.getPlace(place_id)
    return render_template('study_populate.html',polygon=place['polygon'],place_id=place_id,
                           locDist = place['location_distribution'], dataRes = place['data_resolution'], studyID=session['currentStudy'])
                           
@study.route('/place/populate/<place_id>/',methods=['POST'])
def populate_place(place_id):
   location_id = Database.locations.insert({
       'loc': [request.form['lat'],request.form['lng']],
       'type':'gsv',
       'place_id': [place_id],
       'owner': session['userObj']['email'], #TODO: REAL LOGIN SECURITY
       'heading': 0,
       'pitch': 0,
       'votes':0
   })
   Database.qs.update({
       'location_id' : str(location_id), 
       'study_id': str(session['currentStudy']),
       'place_id': place_id
   }, { '$set': {'num_votes' : 0 } }, True)    
   return jsonifyResponse({
       'success': True
   })

@study.route('/place/finish_populate/<place_id>/',methods=['POST'])
def finish_populate_place(place_id):
    if Database.getPlace(place_id) is None:
        return jsonifyResponse({
            'error': 'Place doesn\'t exist!'
        })
    return jsonifyResponse({
        'success': True
    })
    
#--------------------Curate
@study.route('/place/curate/<place_id>/',methods=['GET'])
def curate_study(place_id):
    study_id = session['currentStudy']
    place = Database.getPlace(place_id)
    locations = Database.getLocations(place_id,48)
    return auto_template('study_curate.html',polygon=place['polygon'],locations=locations,place_id=place_id, study_id=study_id)
    
@study.route('/place/curate/location/<id>',methods=['POST'])
def curate_location():    
    # Insert the new study into Mongo
    location = Database.getLocation(id)
    # Return the ID for the client to rendezvous at /study/populate/<id>
    return jsonifyResponse({
        'latitude': str(location.loc[0]),
        'longitude': str(location.loc[1]),
        'heading': str(location.heading),
        'pitch': str(location.pitch)
    })

@study.route('/place/curate/location/update/<id>',methods=['POST'])
def update_location(id):
    lat = request.form['lat']
    lng = request.form['lng']
    heading = request.form['heading']
    pitch = request.form['pitch']
    locationUpdated = Database.updateLocation(id,heading,pitch)
    return jsonifyResponse({
    'success': str(locationUpdated)
    })
    
@study.route('/place/curate/location/delete/<id>',methods=['POST'])
def delete_location(id):
    locationDeleted = Database.deleteLocation(id)
    return jsonifyResponse({
    'success': str(locationDeleted)
    })

@study.route('/study/start/<study_id>/',methods=['GET'])
def start_start(study_id):
    #--Set study to "run"
    
    return auto_template('study_start.html',study_id=study_id)
#--------------------Vote
@study.route("/study/vote/<study_id>/",methods=['POST'])
def post_new_vote(study_id):
    def incVotes(obj):
        obj['votes'] += 1
        Database.locations.save(obj)
        Database.incQSVoteCount(study_id, str(obj.get('_id')))
    leftObj = Database.getLocation(request.form['left'])
    rightObj = Database.getLocation(request.form['right'])
    if leftObj is None or rightObj is None:
        return jsonifyResponse({
            'error': "Locations don't exist!"
        })
    map(incVotes, [leftObj,rightObj])
    newVoteObj = {
        'study_id' : request.form['study_id'],
        'left' : request.form['left'],
        'right' : request.form['right'],
        'choice' : request.form['choice'],
        'timestamp': datetime.now()
    }
    if session.get('userObj'):
        newVoteObj['voter_email'] = session['userObj']['email']
    else:
        if not session.get('voterID'):
            # Generate a random ID to associate votes with this user
            session['voterID'] = str(uuid4().hex)
        newVoteObj['voter_uniqueid'] = session['voterID']    
    Database.votes.insert(newVoteObj)
    return jsonifyResponse({
        'success': True
    })

@study.route("/study/getpair/<study_id>/",methods=['GET'])
def get_study_pairing(study_id):
    # get location 1
    QS1 = Database.randomQS(study_id, fewestVotes=True)
    if QS1 is None:
        return jsonifyResponse({
            'error': "Could not get location 1 from QS collection."
        })
    #get location 2
    if not QS1.has_key('q'): # location 1 has no q score
        QS2 = Database.randomQS(study_id, exclude=QS1.get('location_id')) 
    else:
        #get 25 locations with q scores
        obj = { 
            'study_id': study_id,
            'location_id' : { '$ne' : QS1.get('location_id') },
            'num_votes' : { '$lte' : 30 },
            'q' : { '$exists' : True }
        }
        f = 25
        count = Database.qs.find(obj).count()-1
        s = randint(0,max(0,count-f))
        QSCursor = Database.qs.find(obj).skip(s).limit(f)            
        
        #pick location with closest score
        dist = lambda QS: abs(QS.get('q') - QS1['q'])
        try: 
            QS2 = min(QSCursor, key=dist)
        except ValueError: # db query yields zero results
            QS2 = Database.randomQS(study_id, exclude=QS1.get('location_id')) 
    if QS2 is None:
        return jsonifyResponse({
            'error': "Could not get location 2 from QS collection."
        })
    
    # convert to location objects
    location1 = Database.getLocation(QS1.get('location_id'))
    location2 = Database.getLocation(QS2.get('location_id'))
    locationsToDisplay = [location1, location2]
    if location1 is None or location2 is None:
        return jsonifyResponse({
            'error': "Locations could not be retrieved from location collection!"
        })
    
    return jsonifyResponse({
        'locs' : map(objifyPlace, locationsToDisplay)
    })

#--------------------View
@study.route("/study/view/<study_id>/",methods=['GET'])
def server_view_study(study_id):
    studyObj = Database.getStudy(study_id)
    if studyObj is None:
        return redirect('/')
    return auto_template('view_study.html',study_id=study_id,study_prompt=studyObj.get('study_question'))

@study.route('/location/view/<location_id>/',methods=['GET'])
def get_location(location_id):
    locationCursor = Database.getLocation(location_id)
    lat = locationCursor['loc'][0]
    lng = locationCursor['loc'][1]
    return "<img src='http://maps.googleapis.com/maps/api/streetview?size=404x296&location=" + lat + "," + lng + "&sensor=false'/>"
