from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import json
import os
from datetime import datetime

app = Flask(__name__)

# Render.com Database Configuration
if os.environ.get('DATABASE_URL'):
    # Production (Render)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    # Development (Local)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gopher.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------------------------
# Datenbank-Modelle
# ------------------------------

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    place = db.Column(db.String(100))
    track_count = db.Column(db.Integer)
    players = db.relationship('Player', backref='game', cascade="all, delete-orphan")

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    scores = db.relationship('Score', backref='player', cascade="all, delete-orphan")

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    track = db.Column(db.Integer)
    value = db.Column(db.Integer, default=0)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))

# ------------------------------
# Routen (gleich wie vorher, aber ohne Debug-Prints für Production)
# ------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/save', methods=['POST'])
def save():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'status': 'error', 'message': 'Keine Daten empfangen'}), 400
        
        game = Game(
            date=data.get('date', ''),
            place=data.get('place', ''),
            track_count=data.get('track_count', 18)
        )
        
        db.session.add(game)
        db.session.flush()

        players_data = data.get('players', [])
        
        for i, p in enumerate(players_data):
            player = Player(name=p.get('name', ''), game=game)
            db.session.add(player)
            db.session.flush()
            
            track_count = data.get('track_count', 18)
            for track_num in range(1, track_count + 1):
                score_entry = Score(track=track_num, value=0, player=player)
                db.session.add(score_entry)

        db.session.commit()
        return jsonify({'status': 'success', 'game_id': game.id})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/score/<int:game_id>')
def score_detail(game_id):
    try:
        game = Game.query.get_or_404(game_id)
        players = game.players
        track_count = game.track_count

        score_map = {}
        for player in game.players:
            for score in player.scores:
                score_map[(player.id, score.track)] = score.value

        return render_template(
            'score_detail.html',
            game=game,
            players=players,
            track_count=track_count,
            score_map=score_map
        )
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

@app.route('/update_score', methods=['POST'])
def update_score():
    try:
        data = request.get_json()
        
        player_id = data['player_id']
        track = data['track']
        value = data['value']
        
        score = Score.query.filter_by(player_id=player_id, track=track).first()
        
        if score:
            score.value = value
        else:
            score = Score(player_id=player_id, track=track, value=value)
            db.session.add(score)
        
        db.session.commit()
        
        game = Player.query.get(player_id).game
        totals = {}
        for player in game.players:
            total = sum(s.value for s in player.scores)
            totals[player.id] = total
        
        return jsonify({
            'status': 'success',
            'totals': totals
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/history')
def history():
    try:
        games = Game.query.order_by(Game.id.desc()).all()
        
        games_data = []
        for game in games:
            game_data = {
                'id': game.id,
                'date': game.date,
                'place': game.place,
                'track_count': game.track_count,
                'players': [{'name': p.name} for p in game.players]
            }
            games_data.append(game_data)
        
        return render_template('history.html', games=games, games_data=games_data)
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

@app.route('/delete_game/<int:game_id>', methods=['POST'])
def delete_game(game_id):
    try:
        game = Game.query.get_or_404(game_id)
        db.session.delete(game)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/results/<int:game_id>')
def game_results(game_id):
    try:
        game = Game.query.get_or_404(game_id)
        
        results = []
        for player in game.players:
            total = sum(score.value for score in player.scores)
            results.append({
                'name': player.name,
                'total': total,
                'scores': {score.track: score.value for score in player.scores}
            })
        
        results.sort(key=lambda x: x['total'])
        
        winners = []
        if results and results[0]['total'] > 0:
            min_score = results[0]['total']
            winners = [r for r in results if r['total'] == min_score]
            
            for result in results:
                result['is_winner'] = result['total'] == min_score and result['total'] > 0
                result['is_tie'] = len(winners) > 1 and result['is_winner']
        
        return render_template('results.html', game=game, results=results, winners=winners)
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

@app.route('/initdb')
def initdb():
    try:
        db.create_all()
        return "✅ Datenbank wurde erstellt."
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

# ------------------------------
# App starten
# ------------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # Render.com Port Configuration
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    app.run(host='0.0.0.0', port=port, debug=debug)