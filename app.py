from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import text
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
app = Flask(__name__)

# ------------------------------
# Database Configuration (Render PostgreSQL)
# ------------------------------

def get_database_url():
    """Get PostgreSQL database URL for Render"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL environment variable is required")
    
    # Render uses postgres:// but SQLAlchemy needs postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    logger.info("🐘 Using PostgreSQL (Render)")
    return database_url

app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_timeout': 20,
    'max_overflow': 0,
}

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gopher-production-key')

db = SQLAlchemy(app)
migrate = Migrate(app, db)

def log_action(action, details=""):
    """Centralized logging"""
    logger.info(f"🛡️ PROD: {action} {details}")

# ------------------------------
# Database Models
# ------------------------------

class Place(db.Model):
    """Minigolf-Plätze mit track configuration"""
    __tablename__ = 'places'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    track_count = db.Column(db.Integer, nullable=False, default=18)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    games = db.relationship('Game', backref='place_config', lazy=True)
    place_tracks = db.relationship('PlaceTrack', backref='place', cascade="all, delete-orphan", lazy=True)
    
    def __repr__(self):
        return f'<Place {self.id}: {self.name} ({self.track_count} tracks)>'
    
    def get_track_config(self):
        """Returns dict {track_number: track_type} für diesen Platz"""
        config = {}
        for pt in self.place_tracks:
            config[pt.track_number] = pt.track_type
        return config
    
    def setup_default_tracks(self):
        """Creates default track configuration für neuen Platz"""
        default_track_type = TrackType.query.filter_by(is_default=True).first()
        if not default_track_type:
            default_track_type = TrackType.query.first()
        
        if default_track_type:
            for track_num in range(1, self.track_count + 1):
                existing = PlaceTrack.query.filter_by(place=self, track_number=track_num).first()
                if not existing:
                    place_track = PlaceTrack(
                        place=self, 
                        track_number=track_num, 
                        track_type=default_track_type
                    )
                    db.session.add(place_track)


class TrackType(db.Model):
    """Bibliothek von Bahn-Typen (Standard Icons)"""
    __tablename__ = 'track_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.String(200))
    icon_filename = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    is_placeholder = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    place_tracks = db.relationship('PlaceTrack', backref='track_type', lazy=True)
    
    def __repr__(self):
        return f'<TrackType {self.id}: {self.name}>'
    
    @property
    def icon_url(self):
        """Returns full path to icon"""
        return f'/static/track-icons/{self.icon_filename}'


class PlaceTrack(db.Model):
    """Association Table: Welcher Track-Type für welche Bahn an welchem Platz"""
    __tablename__ = 'place_tracks'
    
    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=False)
    track_number = db.Column(db.Integer, nullable=False)
    track_type_id = db.Column(db.Integer, db.ForeignKey('track_types.id'), nullable=False)
    
    __table_args__ = (
        db.Index('idx_place_track_number', 'place_id', 'track_number'),
        db.UniqueConstraint('place_id', 'track_number', name='uq_place_track_number')
    )
    
    def __repr__(self):
        return f'<PlaceTrack {self.place.name} Track {self.track_number}: {self.track_type.name}>'


class Game(db.Model):
    __tablename__ = 'games'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    place = db.Column(db.String(100), nullable=False)
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=True)
    track_count = db.Column(db.Integer, nullable=False, default=18)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    players = db.relationship('Player', backref='game', cascade="all, delete-orphan", lazy=True)
    
    def __repr__(self):
        return f'<Game {self.id}: {self.place} on {self.date}>'
    
    def get_place_name(self):
        """Returns place name - from Place config or legacy text"""
        if self.place_config:
            return self.place_config.name
        return self.place
    
    def get_track_config(self):
        """Returns track configuration für diese Game"""
        if self.place_config:
            return self.place_config.get_track_config()
        return {}


class Player(db.Model):
    __tablename__ = 'players'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    
    # Relationships
    scores = db.relationship('Score', backref='player', cascade="all, delete-orphan", lazy=True)
    
    def __repr__(self):
        return f'<Player {self.id}: {self.name}>'
    
    def get_total_score(self):
        """Calculate total score for this player"""
        return sum(score.value for score in self.scores)

class Score(db.Model):
    __tablename__ = 'scores'
    
    id = db.Column(db.Integer, primary_key=True)
    track = db.Column(db.Integer, nullable=False)
    value = db.Column(db.Integer, nullable=False, default=0)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    
    __table_args__ = (db.Index('idx_player_track', 'player_id', 'track'),)
    
    def __repr__(self):
        return f'<Score {self.id}: Track {self.track} = {self.value}>'

# ------------------------------
# Database Management
# ------------------------------

def check_database_connection():
    """Test database connection"""
    try:
        db.session.execute(text('SELECT 1'))
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        return False

def check_tables_exist():
    """Check if all required tables exist"""
    try:
        db.session.execute(text('SELECT 1 FROM games LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM players LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM scores LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM places LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM track_types LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM place_tracks LIMIT 1'))
        return True
    except Exception:
        return False

def initialize_default_data():
    """Setup default Track Types"""
    default_track_types = [
        {'name': 'Standard', 'description': 'Standard Minigolf Bahn', 'icon_filename': 'bahn_placeholder.png', 'is_default': True, 'sort_order': 1},
        {'name': 'Kurve Links', 'description': 'Linkskurve', 'icon_filename': 'bahn_kurve_links.png', 'sort_order': 2},
        {'name': 'Kurve Rechts', 'description': 'Rechtskurve', 'icon_filename': 'bahn_kurve_rechts.png', 'sort_order': 3},
        {'name': 'Hindernis', 'description': 'Bahn mit Hindernis', 'icon_filename': 'bahn_hindernis.png', 'sort_order': 4},
        {'name': 'Brücke', 'description': 'Brücken-Bahn', 'icon_filename': 'bahn_bruecke.png', 'sort_order': 5},
        {'name': 'Windmühle', 'description': 'Bahn mit Windmühle', 'icon_filename': 'windmill.png', 'sort_order': 6},
        {'name': 'Rampe', 'description': 'Rampen-Bahn', 'icon_filename': 'ramp.png', 'sort_order': 7},
        {'name': 'Tunnel', 'description': 'Tunnel-Bahn', 'icon_filename': 'tunnel.png', 'sort_order': 8},
        {'name': 'Unbekannt', 'description': 'Platzhalter für unbekannte Bahn-Typen', 'icon_filename': 'bahn_placeholder.png', 'is_placeholder': True, 'sort_order': 99},
    ]
    
    for tt_data in default_track_types:
        existing = TrackType.query.filter_by(name=tt_data['name']).first()
        if not existing:
            track_type = TrackType(**tt_data)
            db.session.add(track_type)
    
    db.session.commit()
    log_action("Track Types initialized")

def migrate_legacy_games():
    """Convert legacy games to use Place references"""
    legacy_games = Game.query.filter(Game.place_id == None).all()
    
    for game in legacy_games:
        existing_place = Place.query.filter_by(name=game.place).first()
        
        if not existing_place:
            new_place = Place(name=game.place, track_count=game.track_count)
            db.session.add(new_place)
            db.session.flush()
            new_place.setup_default_tracks()
            game.place_id = new_place.id
        else:
            game.place_id = existing_place.id
    
    db.session.commit()
    log_action(f"Migrated {len(legacy_games)} legacy games to Place references")

def safe_database_init():
    """Database initialization"""
    try:
        if not check_database_connection():
            raise Exception("Database connection failed")
        
        db.create_all()
        initialize_default_data()
        migrate_legacy_games()
        
        log_action("Database initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        return False

# ------------------------------
# Auto-Initialization
# ------------------------------

@app.before_request
def ensure_database():
    """Automatically ensure database tables exist"""
    if request.endpoint == 'static':
        return
    
    if not hasattr(app, '_database_checked'):
        try:
            if check_database_connection():
                if not check_tables_exist():
                    log_action("Creating database tables automatically")
                    safe_database_init()
                
                app._database_checked = True
            else:
                logger.error("❌ Database connection failed")
                
        except Exception as e:
            logger.error(f"❌ Database auto-check error: {str(e)}")

# ------------------------------
# Main Routes
# ------------------------------

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/save', methods=['POST'])
def save():
    """Save new game with places support"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'status': 'error', 'message': 'No data received'}), 400
        
        # Validate required fields
        required_fields = ['date', 'place', 'players']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'status': 'error', 'message': f'Missing required field: {field}'}), 400
        
        place_name = data.get('place').strip()
        track_count = data.get('track_count', 18)
        
        # Find or create place
        place = Place.query.filter_by(name=place_name).first()
        place_id = None
        
        if place:
            place_id = place.id
            track_count = place.track_count
        else:
            new_place = Place(name=place_name, track_count=track_count)
            db.session.add(new_place)
            db.session.flush()
            new_place.setup_default_tracks()
            place_id = new_place.id
            log_action(f"Auto-created place: {place_name}")
        
        # Create game
        game = Game(
            date=data.get('date'),
            place=place_name,
            place_id=place_id,
            track_count=track_count
        )
        
        db.session.add(game)
        db.session.flush()
        
        # Create players and scores
        players_data = data.get('players', [])
        
        for player_data in players_data:
            if not player_data.get('name', '').strip():
                db.session.rollback()
                return jsonify({'status': 'error', 'message': 'Player name cannot be empty'}), 400
            
            player = Player(name=player_data['name'].strip(), game=game)
            db.session.add(player)
            db.session.flush()
            
            # Create initial scores (all 0)
            for track_num in range(1, track_count + 1):
                score = Score(track=track_num, value=0, player=player)
                db.session.add(score)
        
        db.session.commit()
        
        log_action(f"Game created: {place_name} ({len(players_data)} players, {track_count} tracks)")
        
        return jsonify({
            'status': 'success', 
            'game_id': game.id,
            'place_id': place_id,
            'message': f'Game created successfully with {len(players_data)} players'
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Save error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to save game'}), 500

@app.route('/score/<int:game_id>')
def score_detail(game_id):
    """Score input page for a specific game"""
    try:
        game = Game.query.get_or_404(game_id)
        
        score_map = {}
        for player in game.players:
            for score in player.scores:
                score_map[(player.id, score.track)] = score.value
        
        log_action(f"Score page accessed for game {game_id}")
        
        return render_template(
            'score_detail.html',
            game=game,
            players=game.players,
            track_count=game.track_count,
            score_map=score_map
        )
        
    except Exception as e:
        logger.error(f"❌ Score detail error: {str(e)}")
        return f"<h1>Error</h1><p>Game not found or error loading game.</p>", 404

@app.route('/update_score', methods=['POST'])
def update_score():
    """Update a player's score for a specific track"""
    try:
        data = request.get_json()
        
        required_fields = ['player_id', 'track', 'value']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'Missing field: {field}'}), 400
        
        player_id = int(data['player_id'])
        track = int(data['track'])
        value = int(data['value'])
        
        if value < 0 or value > 20:
            return jsonify({'status': 'error', 'message': 'Score must be between 0 and 20'}), 400
        
        score = Score.query.filter_by(player_id=player_id, track=track).first()
        
        if score:
            score.value = value
        else:
            score = Score(player_id=player_id, track=track, value=value)
            db.session.add(score)
        
        db.session.commit()
        
        # Calculate new totals for all players in this game
        player = Player.query.get(player_id)
        game = player.game
        
        totals = {}
        for p in game.players:
            totals[p.id] = p.get_total_score()
        
        log_action(f"Score updated: Player {player_id}, Track {track} = {value}")
        
        return jsonify({
            'status': 'success',
            'totals': totals,
            'message': 'Score updated successfully'
        })
    
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid number format'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Update score error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to update score'}), 500

@app.route('/history')
def history():
    """Game history page with track icons support"""
    try:
        games = Game.query.order_by(Game.id.desc()).all()
        
        games_data = []
        for game in games:
            track_icons = {}
            has_track_config = False
            
            if game.place_config and game.place_config.place_tracks:
                has_track_config = True
                place_track_map = {pt.track_number: pt for pt in game.place_config.place_tracks}
                
                for track_num in range(1, game.track_count + 1):
                    if track_num in place_track_map:
                        track_icons[track_num] = place_track_map[track_num].track_type.icon_url
                    else:
                        track_icons[track_num] = '/static/track-icons/bahn_placeholder.png'
            else:
                for track_num in range(1, game.track_count + 1):
                    track_icons[track_num] = '/static/track-icons/bahn_placeholder.png'
            
            game_data = {
                'id': game.id,
                'date': game.date,
                'place': game.place,
                'place_id': game.place_id,
                'track_count': game.track_count,
                'players': [{'name': p.name, 'total': p.get_total_score()} for p in game.players],
                'player_count': len(game.players),
                'has_track_config': has_track_config,
                'track_icons': track_icons
            }
            games_data.append(game_data)
        
        log_action(f"History accessed ({len(games)} games)")
        
        return render_template('history.html', games=games, games_data=games_data)
        
    except Exception as e:
        logger.error(f"❌ History error: {str(e)}")
        return f"<h1>Error</h1><p>Failed to load game history.</p>", 500

@app.route('/delete_game/<int:game_id>', methods=['POST'])
def delete_game(game_id):
    """Delete a game and all associated data"""
    try:
        game = Game.query.get_or_404(game_id)
        game_info = f"{game.place} on {game.date}"
        
        db.session.delete(game)
        db.session.commit()
        
        log_action(f"Game deleted: {game_info}")
        
        return jsonify({'status': 'success', 'message': 'Game deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Delete error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to delete game'}), 500

@app.route('/results/<int:game_id>')
def game_results(game_id):
    """Final results page for a game"""
    try:
        game = Game.query.get_or_404(game_id)
        
        results = []
        for player in game.players:
            total = player.get_total_score()
            result = {
                'name': player.name,
                'total': total,
                'scores': {score.track: score.value for score in player.scores}
            }
            results.append(result)
        
        results.sort(key=lambda x: x['total'])
        
        winners = []
        if results and results[0]['total'] > 0:
            min_score = results[0]['total']
            winners = [r for r in results if r['total'] == min_score]
            
            for result in results:
                result['is_winner'] = result['total'] == min_score
                result['is_tie'] = len(winners) > 1 and result['is_winner']
        
        log_action(f"Results viewed for game {game_id}")
        
        return render_template('results.html', game=game, results=results, winners=winners)
        
    except Exception as e:
        logger.error(f"❌ Results error: {str(e)}")
        return f"<h1>Error</h1><p>Game not found or error loading results.</p>", 404

@app.route('/settings')
def settings():
    """Settings page with real data"""
    try:
        stats = {
            'places_count': Place.query.count(),
            'track_types_count': TrackType.query.count(),
            'games_count': Game.query.count(),
            'players_count': Player.query.count(),
            'scores_count': Score.query.count()
        }
        
        places = Place.query.order_by(Place.is_default.desc(), Place.name).all()
        track_types = TrackType.query.order_by(TrackType.sort_order).all()
        
        return render_template('settings.html', 
                             stats=stats, 
                             places=places, 
                             track_types=track_types)
        
    except Exception as e:
        logger.error(f"❌ Settings page error: {str(e)}")
        return f"<h1>Settings</h1><p>Error loading settings: {str(e)}</p>", 500

# ------------------------------
# API Endpoints - COMPLETE SET
# ------------------------------

@app.route('/api/places', methods=['GET'])
def get_places():
    """Get all places - Production version"""
    try:
        if not check_database_connection():
            return jsonify({'status': 'error', 'message': 'Database not connected', 'places': []}), 503
        
        if not check_tables_exist():
            return jsonify({'status': 'error', 'message': 'Database tables not found', 'places': []}), 503
        
        places = Place.query.all()
        places_data = []
        
        for place in places:
            try:
                place_data = {
                    'id': place.id,
                    'name': place.name,
                    'track_count': place.track_count,
                    'is_default': place.is_default,
                    'has_custom_config': False
                }
                
                if hasattr(place, 'place_tracks') and place.place_tracks:
                    place_data['has_custom_config'] = len(place.place_tracks) > 0
                
                places_data.append(place_data)
                
            except Exception as place_error:
                logger.error(f"Error processing place {place.id}: {str(place_error)}")
                continue
        
        places_data.sort(key=lambda x: (not x.get('is_default', False), x.get('name', '')))
        
        return jsonify({
            'status': 'success',
            'places': places_data,
            'count': len(places_data)
        })
        
    except Exception as e:
        logger.error(f"❌ Get places API error: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Internal server error: {str(e)}', 'places': []}), 500

@app.route('/api/places', methods=['POST'])
def create_place():
    """Create new place"""
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'status': 'error', 'message': 'Name required'}), 400
        
        place_name = data.get('name').strip()
        track_count = int(data.get('track_count', 18))
        is_default = data.get('is_default', False)
        
        if Place.query.filter_by(name=place_name).first():
            return jsonify({'status': 'error', 'message': 'Place already exists'}), 400
        
        new_place = Place(name=place_name, track_count=track_count, is_default=is_default)
        db.session.add(new_place)
        db.session.flush()
        new_place.setup_default_tracks()
        db.session.commit()
        
        log_action(f"Place created via API: {place_name}")
        return jsonify({'status': 'success', 'place_id': new_place.id})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Create place error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/places/<int:place_id>', methods=['PUT'])
def update_place(place_id):
    """Update existing place"""
    try:
        place = Place.query.get_or_404(place_id)
        data = request.get_json()
        
        if 'name' in data:
            place.name = data['name'].strip()
        if 'track_count' in data:
            place.track_count = int(data['track_count'])
        if 'is_default' in data:
            place.is_default = data['is_default']
        
        db.session.commit()
        log_action(f"Place updated via API: {place.name}")
        return jsonify({'status': 'success'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update place error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/places/<int:place_id>', methods=['DELETE'])
def delete_place_api(place_id):
    """Delete place"""
    try:
        place = Place.query.get_or_404(place_id)
        place_name = place.name
        
        games_count = Game.query.filter_by(place_id=place_id).count()
        if games_count > 0:
            return jsonify({'status': 'error', 'message': f'Place used by {games_count} games'}), 400
        
        db.session.delete(place)
        db.session.commit()
        
        log_action(f"Place deleted via API: {place_name}")
        return jsonify({'status': 'success'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Delete place error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/track-types', methods=['GET'])  
def get_track_types():
    """Get all track types"""
    try:
        if not check_database_connection():
            return jsonify({'status': 'error', 'message': 'Database not connected'}), 503
        
        if not check_tables_exist():
            return jsonify({'status': 'error', 'message': 'Tables do not exist'}), 503
        
        track_types = TrackType.query.order_by(TrackType.sort_order, TrackType.name).all()
        track_types_data = []
        
        for tt in track_types:
            try:
                track_types_data.append({
                    'id': tt.id,
                    'name': tt.name,
                    'description': tt.description or '',
                    'icon_url': tt.icon_url,
                    'icon_filename': tt.icon_filename,
                    'is_default': tt.is_default,
                    'is_placeholder': tt.is_placeholder
                })
            except Exception as tt_error:
                logger.error(f"Error processing track type {tt.id}: {str(tt_error)}")
                continue
        
        return jsonify({
            'status': 'success',
            'track_types': track_types_data,
            'count': len(track_types_data)
        })
        
    except Exception as e:
        logger.error(f"❌ Get track types API error: {str(e)}")
        return jsonify({'status': 'error', 'message': f'API Error: {str(e)}'}), 500

@app.route('/api/places/<int:place_id>/tracks')
def get_place_track_config(place_id):
    """Get track configuration for a specific place"""
    try:
        place = Place.query.get_or_404(place_id)
        
        track_config = []
        place_track_map = {pt.track_number: pt for pt in place.place_tracks}
        
        for track_num in range(1, place.track_count + 1):
            if track_num in place_track_map:
                pt = place_track_map[track_num]
                track_config.append({
                    'track_number': track_num,
                    'track_type_id': pt.track_type_id,
                    'track_type_name': pt.track_type.name,
                    'icon_url': pt.track_type.icon_url
                })
            else:
                default_type = TrackType.query.filter_by(is_default=True).first()
                track_config.append({
                    'track_number': track_num,
                    'track_type_id': default_type.id if default_type else None,
                    'track_type_name': default_type.name if default_type else 'Standard',
                    'icon_url': default_type.icon_url if default_type else '/static/track-icons/bahn_placeholder.png'
                })
        
        return jsonify({
            'status': 'success',
            'place': {
                'id': place.id,
                'name': place.name,
                'track_count': place.track_count
            },
            'track_config': track_config
        })
        
    except Exception as e:
        logger.error(f"❌ Get place track config error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/places/<int:place_id>/tracks/<int:track_number>', methods=['PUT'])
def update_single_track_type(place_id, track_number):
    """Update track type for a specific track at a place"""
    try:
        place = Place.query.get_or_404(place_id)
        data = request.get_json()
        
        if not data or 'track_type_id' not in data:
            return jsonify({'status': 'error', 'message': 'track_type_id required'}), 400
        
        track_type_id = int(data['track_type_id'])
        track_type = TrackType.query.get_or_404(track_type_id)
        
        # Validate track number
        if track_number < 1 or track_number > place.track_count:
            return jsonify({'status': 'error', 'message': 'Invalid track number'}), 400
        
        # Find or create PlaceTrack
        place_track = PlaceTrack.query.filter_by(place_id=place_id, track_number=track_number).first()
        
        if place_track:
            place_track.track_type_id = track_type_id
        else:
            place_track = PlaceTrack(
                place_id=place_id,
                track_number=track_number,
                track_type_id=track_type_id
            )
            db.session.add(place_track)
        
        db.session.commit()
        
        log_action(f"Track type updated: Place {place.name}, Track {track_number} -> {track_type.name}")
        
        return jsonify({
            'status': 'success',
            'message': f'Track {track_number} updated to {track_type.name}',
            'track': {
                'track_number': track_number,
                'track_type_id': track_type_id,
                'track_type_name': track_type.name,
                'icon_url': track_type.icon_url
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Update single track type error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/places/<int:place_id>/tracks', methods=['PUT'])
def update_place_track_config(place_id):
    """Update complete track configuration for a place"""
    try:
        place = Place.query.get_or_404(place_id)
        data = request.get_json()
        
        if not data or 'track_config' not in data:
            return jsonify({'status': 'error', 'message': 'track_config required'}), 400
        
        track_config = data['track_config']
        updated_tracks = 0
        
        for track_data in track_config:
            track_number = track_data.get('track_number')
            track_type_id = track_data.get('track_type_id')
            
            if not track_number or not track_type_id:
                continue
            
            # Validate track number
            if track_number < 1 or track_number > place.track_count:
                continue
            
            # Validate track type exists
            if not TrackType.query.get(track_type_id):
                continue
            
            # Find or create PlaceTrack
            place_track = PlaceTrack.query.filter_by(place_id=place_id, track_number=track_number).first()
            
            if place_track:
                place_track.track_type_id = track_type_id
            else:
                place_track = PlaceTrack(
                    place_id=place_id,
                    track_number=track_number,
                    track_type_id=track_type_id
                )
                db.session.add(place_track)
            
            updated_tracks += 1
        
        db.session.commit()
        
        log_action(f"Track config updated: Place {place.name}, {updated_tracks} tracks")
        
        return jsonify({
            'status': 'success',
            'message': f'Updated {updated_tracks} tracks',
            'updated_tracks': updated_tracks
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Update place track config error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/debug/track-icons')
def debug_track_icons():
    """Debug endpoint to check track icon files"""
    try:
        # Get all track types from database
        track_types = TrackType.query.all()
        track_types_data = []
        
        for tt in track_types:
            track_types_data.append({
                'id': tt.id,
                'name': tt.name,
                'icon_filename': tt.icon_filename,
                'icon_url': tt.icon_url
            })
        
        # Check which icon files exist in static folder
        import os
        static_path = os.path.join(app.root_path, 'static', 'track-icons')
        available_files = []
        
        if os.path.exists(static_path):
            available_files = [f for f in os.listdir(static_path) if f.endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif'))]
        
        # Find missing icons
        missing_icons = []
        for tt in track_types_data:
            if tt['icon_filename'] not in available_files:
                missing_icons.append({
                    'track_type': tt['name'],
                    'filename': tt['icon_filename']
                })
        
        debug_info = {
            'status': 'success',
            'track_types': track_types_data,
            'files': available_files,
            'missing_icons': missing_icons,
            'static_path': static_path,
            'files_count': len(available_files),
            'track_types_count': len(track_types_data),
            'missing_count': len(missing_icons)
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        logger.error(f"❌ Debug track icons error: {str(e)}")
        return jsonify({
            'status': 'error', 
            'message': str(e),
            'track_types': [],
            'files': [],
            'missing_icons': []
        }), 500

# ------------------------------
# Health Check
# ------------------------------

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        db_status = check_database_connection()
        tables_exist = check_tables_exist() if db_status else False
        
        game_count = Game.query.count() if db_status and tables_exist else 0
        place_count = Place.query.count() if db_status and tables_exist else 0
        
        status = {
            'status': 'healthy' if (db_status and tables_exist) else 'unhealthy',
            'database': 'connected' if db_status else 'disconnected',
            'tables': 'exist' if tables_exist else 'missing',
            'games_count': game_count,
            'places_count': place_count,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(status), 200 if (db_status and tables_exist) else 503
      
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ------------------------------
# Error Handlers
# ------------------------------

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return f"<h1>404 - Page Not Found</h1><p>The requested page was not found.</p><a href='/'>🏠 Home</a>", 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    logger.error(f"❌ Internal server error: {str(error)}")
    return f"<h1>500 - Internal Server Error</h1><p>Something went wrong.</p><a href='/'>🏠 Home</a>", 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Handle unexpected exceptions"""
    logger.error(f"❌ Unhandled exception: {str(e)}")
    db.session.rollback()
    return f"<h1>🏌️ Gopher Minigolf</h1><p>Something went wrong. Please try again.</p><a href='/'>🏠 Home</a>", 500

# ------------------------------
# Application Startup
# ------------------------------

def initialize_app():
    """Initialize the application on startup"""
    try:
        log_action("🚀 Gopher Minigolf App initializing")
        
        if check_database_connection():
            log_action("Database connection successful")
            
            if not check_tables_exist():
                log_action("Creating database tables on startup")
                success = safe_database_init()
                if success:
                    log_action("✅ Startup database initialization successful")
                else:
                    logger.error("❌ Startup database initialization failed")
            else:
                log_action("Database tables already exist")
        else:
            logger.error("❌ Database connection failed on startup")
            
        log_action("✅ Application initialization complete")
        
    except Exception as e:
        logger.error(f"❌ Application initialization error: {str(e)}")

# Initialize app for Gunicorn
with app.app_context():
    try:
        initialize_app()
    except Exception as e:
        logger.error(f"⚠️ App context initialization warning: {e}")

# For Render.com Gunicorn startup
try:
    with app.app_context():
        if not check_tables_exist():
            logger.info("🔧 Gunicorn startup: Creating tables")
            safe_database_init()
except Exception as e:
    logger.error(f"❌ Gunicorn startup error: {e}")