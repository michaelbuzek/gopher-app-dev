from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import json
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ------------------------------
# Database Configuration (Render-optimized)
# ------------------------------

def get_database_url():
    """Get database URL with proper PostgreSQL handling for Render"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Render uses postgres:// but SQLAlchemy needs postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        logger.info("🐘 Using PostgreSQL (Render)")
        return database_url
    else:
        logger.info("🗄️ Using SQLite (Local)")
        return 'sqlite:///gopher.db'

app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Handle database disconnections
    'pool_recycle': 300,    # Recycle connections every 5 minutes
}

db = SQLAlchemy(app)

# ------------------------------
# Environment Helper Functions
# ------------------------------

def get_environment():
    """Get current environment with fallback"""
    return os.environ.get('ENVIRONMENT', 'development').lower()

def is_development():
    """Check if we're in development environment"""
    return get_environment() == 'development'

def is_production():
    """Check if we're in production environment"""
    return get_environment() == 'production'

def log_action(action, details=""):
    """Centralized logging with environment awareness"""
    env_prefix = "🔧 DEV" if is_development() else "🛡️ PROD"
    logger.info(f"{env_prefix}: {action} {details}")

# ------------------------------
# Database Models
# ------------------------------

class Place(db.Model):
    """Minigolf-Plätze mit track configuration"""
    __tablename__ = 'places'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    track_count = db.Column(db.Integer, nullable=False, default=18)
    is_default = db.Column(db.Boolean, default=False)  # Für "Bülach" Standard
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
        # Standard Track Type (wenn noch keine spezifische config)
        default_track_type = TrackType.query.filter_by(is_default=True).first()
        if not default_track_type:
            # Fallback: ersten verfügbaren Track Type nehmen
            default_track_type = TrackType.query.first()
        
        if default_track_type:
            for track_num in range(1, self.track_count + 1):
                # Nur erstellen wenn noch nicht existiert
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
    icon_filename = db.Column(db.String(100), nullable=False)  # z.B. "bahn_1.png"
    is_default = db.Column(db.Boolean, default=False)  # Standard Track Type
    is_placeholder = db.Column(db.Boolean, default=False)  # Platzhalter für unbekannte
    sort_order = db.Column(db.Integer, default=0)  # Reihenfolge in Dropdown
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
    track_number = db.Column(db.Integer, nullable=False)  # Bahn 1, 2, 3, etc.
    track_type_id = db.Column(db.Integer, db.ForeignKey('track_types.id'), nullable=False)
    
    # Composite index für Performance & Eindeutigkeit
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
    place = db.Column(db.String(100), nullable=False)  # BEHALTEN für Legacy Games
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=True)  # NEU: Referenz zu Place
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
        return {}  # Legacy games haben keine track config


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
    
    # Composite index for performance
    __table_args__ = (db.Index('idx_player_track', 'player_id', 'track'),)
    
    def __repr__(self):
        return f'<Score {self.id}: Track {self.track} = {self.value}>'

# ------------------------------
# Database Management & Health Check
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
        # Try to query each table
        db.session.execute(text('SELECT 1 FROM games LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM players LIMIT 1'))
        db.session.execute(text('SELECT 1 FROM scores LIMIT 1'))
        return True
    except Exception:
        return False

def initialize_default_data():
    """Setup default Places & Track Types"""
    
    # 1. Standard Track Types erstellen
    default_track_types = [
        {'name': 'Standard', 'description': 'Standard Minigolf Bahn', 'icon_filename': 'bahn_standard.png', 'is_default': True, 'sort_order': 1},
        {'name': 'Kurve Links', 'description': 'Linkskurve', 'icon_filename': 'bahn_kurve_links.png', 'sort_order': 2},
        {'name': 'Kurve Rechts', 'description': 'Rechtskurve', 'icon_filename': 'bahn_kurve_rechts.png', 'sort_order': 3},
        {'name': 'Hindernis', 'description': 'Bahn mit Hindernis', 'icon_filename': 'bahn_hindernis.png', 'sort_order': 4},
        {'name': 'Brücke', 'description': 'Brücken-Bahn', 'icon_filename': 'bahn_bruecke.png', 'sort_order': 5},
        {'name': 'Unbekannt', 'description': 'Platzhalter für unbekannte Bahn-Typen', 'icon_filename': 'bahn_placeholder.png', 'is_placeholder': True, 'sort_order': 99},
    ]
    
    for tt_data in default_track_types:
        existing = TrackType.query.filter_by(name=tt_data['name']).first()
        if not existing:
            track_type = TrackType(**tt_data)
            db.session.add(track_type)
    
    # 2. Standard Place "Bülach" erstellen
    bulach = Place.query.filter_by(name='Bülach').first()
    if not bulach:
        bulach = Place(name='Bülach', track_count=18, is_default=True)
        db.session.add(bulach)
        db.session.flush()  # Get ID
        
        # Standard track configuration für Bülach
        bulach.setup_default_tracks()
    
    db.session.commit()
    log_action("Default Places & Track Types initialized")


def migrate_legacy_games():
    """Convert legacy games to use Place references"""
    legacy_games = Game.query.filter(Game.place_id == None).all()
    
    for game in legacy_games:
        # Versuche existing Place zu finden
        existing_place = Place.query.filter_by(name=game.place).first()
        
        if not existing_place:
            # Erstelle neuen Place für diesen legacy game
            new_place = Place(name=game.place, track_count=game.track_count)
            db.session.add(new_place)
            db.session.flush()  # Get ID
            new_place.setup_default_tracks()
            game.place_id = new_place.id
        else:
            game.place_id = existing_place.id
    
    db.session.commit()
    log_action(f"Migrated {len(legacy_games)} legacy games to Place references")


def safe_database_init():
    """Updated database initialization"""
    try:
        if not check_database_connection():
            raise Exception("Database connection failed")
        
        # Create all tables (including new ones)
        db.create_all()
        
        # Initialize default data
        initialize_default_data()
        
        # Migrate legacy games (if any)
        migrate_legacy_games()
        
        log_action("Database tables and default data initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        return False

# ------------------------------
# AUTOMATIC DATABASE INITIALIZATION
# ------------------------------

@app.before_request
def ensure_database():
    """Automatically ensure database tables exist before each request"""
    # Skip for static files and health checks
    if request.endpoint in ['static', 'health_check']:
        return
    
    # Only check once per app instance
    if not hasattr(app, '_database_checked'):
        try:
            log_action("Checking database tables...")
            
            if check_database_connection():
                if not check_tables_exist():
                    log_action("Tables missing - creating automatically")
                    success = safe_database_init()
                    if success:
                        log_action("✅ Database auto-initialization successful")
                    else:
                        logger.error("❌ Database auto-initialization failed")
                else:
                    log_action("✅ Database tables verified")
                
                app._database_checked = True
            else:
                logger.error("❌ Database connection failed during auto-check")
                
        except Exception as e:
            logger.error(f"❌ Database auto-check error: {str(e)}")

# ------------------------------
# Health Check & Manual Init Routes
# ------------------------------

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        # Check database connection
        db_status = check_database_connection()
        tables_exist = check_tables_exist() if db_status else False
        
        # Get basic stats
        game_count = Game.query.count() if db_status and tables_exist else 0
        
        status = {
            'status': 'healthy' if (db_status and tables_exist) else 'unhealthy',
            'environment': get_environment(),
            'database': 'connected' if db_status else 'disconnected',
            'tables': 'exist' if tables_exist else 'missing',
            'games_count': game_count,
            'auto_init': 'enabled',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(status), 200 if (db_status and tables_exist) else 503
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/initdb')
def initdb():
    """Manual database initialization - now mostly for debugging"""
    try:
        if is_development():
            # Development: Allow optional reset
            reset_requested = request.args.get('reset', '').lower() == 'true'
            
            if reset_requested:
                log_action("Manual database reset (development only)")
                db.drop_all()
                
            success = safe_database_init()
            
            if success:
                action = "reset and created" if reset_requested else "initialized"
                log_action(f"Manual database {action}")
                return f"✅ Development: Database {action} successfully.<br><small>Note: Auto-initialization is now enabled!</small>"
            else:
                return "❌ Database initialization failed.", 500
                
        else:
            # Production: Only safe initialization
            success = safe_database_init()
            
            if success:
                log_action("Manual database initialization")
                return "✅ Production: Database safely initialized.<br><small>Note: This should happen automatically now!</small>"
            else:
                return "❌ Database initialization failed.", 500
                
    except Exception as e:
        logger.error(f"❌ Manual database init error: {str(e)}")
        return f"<h1>Database Error</h1><p>{str(e)}</p>", 500

@app.route('/reset-dev-db')
def reset_dev_db():
    """Development only: Force reset database"""
    if not is_production():
        log_action("Unauthorized reset attempt blocked")
        return jsonify({'error': 'Only available in development environment'}), 403
    
    try:
        log_action("Performing complete database reset")
        db.drop_all()
        success = safe_database_init()
        
        # Reset the check flag so auto-init runs again
        if hasattr(app, '_database_checked'):
            delattr(app, '_database_checked')
        
        if success:
            log_action("Database reset completed")
            return "✅ Development: Database completely reset."
        else:
            return "❌ Database reset failed.", 500
            
    except Exception as e:
        logger.error(f"❌ Reset error: {str(e)}")
        return f"<h1>Reset Error</h1><p>{str(e)}</p>", 500

@app.route('/db-info')
def db_info():
    """Database information and statistics"""
    try:
        # Connection test
        db_connected = check_database_connection()
        tables_exist = check_tables_exist() if db_connected else False
        
        if not db_connected:
            return jsonify({'error': 'Database not connected'}), 503
        
        # Gather statistics
        stats = {
            'environment': get_environment(),
            'database_type': 'PostgreSQL' if 'postgresql://' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite',
            'connection_status': 'connected',
            'tables_status': 'exist' if tables_exist else 'missing',
            'auto_initialization': 'enabled',
            'tables': {
                'games': Game.query.count() if tables_exist else 0,
                'players': Player.query.count() if tables_exist else 0,
                'scores': Score.query.count() if tables_exist else 0
            } if tables_exist else 'tables_missing',
            'latest_game': None,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Get latest game info
        if tables_exist:
            latest_game = Game.query.order_by(Game.id.desc()).first()
            if latest_game:
                stats['latest_game'] = {
                    'id': latest_game.id,
                    'place': latest_game.place,
                    'date': latest_game.date,
                    'players': len(latest_game.players)
                }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"❌ DB info error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ------------------------------
# Main Application Routes
# ------------------------------

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/save', methods=['POST'])
def save():
    """Save new game with places support - UPDATED VERSION"""
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
            # Use place's track count if provided
            track_count = place.track_count
        else:
            # Create new place on-the-fly
            new_place = Place(name=place_name, track_count=track_count)
            db.session.add(new_place)
            db.session.flush()  # Get ID
            new_place.setup_default_tracks()
            place_id = new_place.id
            log_action(f"Auto-created place: {place_name}")
        
        # Create game
        game = Game(
            date=data.get('date'),
            place=place_name,  # Keep for compatibility
            place_id=place_id,  # NEW: Reference to Place
            track_count=track_count
        )
        
        db.session.add(game)
        db.session.flush()  # Get game.id
        
        # Create players and scores (same as before)
        players_data = data.get('players', [])
        
        for player_data in players_data:
            if not player_data.get('name', '').strip():
                db.session.rollback()
                return jsonify({'status': 'error', 'message': 'Player name cannot be empty'}), 400
            
            player = Player(name=player_data['name'].strip(), game=game)
            db.session.add(player)
            db.session.flush()  # Get player.id
            
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
        
        # Build score map for template
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
        
        # Validate input
        required_fields = ['player_id', 'track', 'value']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'Missing field: {field}'}), 400
        
        player_id = int(data['player_id'])
        track = int(data['track'])
        value = int(data['value'])
        
        # Validate score value
        if value < 0 or value > 20:  # Reasonable limits
            return jsonify({'status': 'error', 'message': 'Score must be between 0 and 20'}), 400
        
        # Find and update score
        score = Score.query.filter_by(player_id=player_id, track=track).first()
        
        if score:
            score.value = value
        else:
            # Create new score if doesn't exist
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
    """Game history page"""
    try:
        games = Game.query.order_by(Game.id.desc()).all()
        
        # Prepare games data for template
        games_data = []
        for game in games:
            game_data = {
                'id': game.id,
                'date': game.date,
                'place': game.place,
                'track_count': game.track_count,
                'players': [{'name': p.name, 'total': p.get_total_score()} for p in game.players],
                'player_count': len(game.players)
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
        
        # Calculate results
        results = []
        for player in game.players:
            total = player.get_total_score()
            result = {
                'name': player.name,
                'total': total,
                'scores': {score.track: score.value for score in player.scores}
            }
            results.append(result)
        
        # Sort by total score (lowest wins)
        results.sort(key=lambda x: x['total'])
        
        # Determine winners (handle ties)
        winners = []
        if results and results[0]['total'] > 0:
            min_score = results[0]['total']
            winners = [r for r in results if r['total'] == min_score]
            
            # Mark winners and ties
            for result in results:
                result['is_winner'] = result['total'] == min_score
                result['is_tie'] = len(winners) > 1 and result['is_winner']
        
        log_action(f"Results viewed for game {game_id}")
        
        return render_template('results.html', game=game, results=results, winners=winners)
        
    except Exception as e:
        logger.error(f"❌ Results error: {str(e)}")
        return f"<h1>Error</h1><p>Game not found or error loading results.</p>", 404

# ------------------------------
# TEMPORARY API Endpoints (Quick Fix)
# ------------------------------

@app.route('/api/places', methods=['GET'])
def get_places_temp():
    """Temporary places API mit fake data"""
    try:
        # Fake data für jetzt
        fake_places = [
            {
                'id': 1,
                'name': 'Bülach',
                'track_count': 18,
                'is_default': True,
                'has_custom_config': False
            },
            {
                'id': 2, 
                'name': 'Adventure Golf Bern',
                'track_count': 12,
                'is_default': False,
                'has_custom_config': False
            }
        ]
        
        return jsonify({
            'status': 'success',
            'places': fake_places
        })
        
    except Exception as e:
        logger.error(f"❌ Get places error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to load places'}), 500

@app.route('/api/track-types', methods=['GET'])  
def get_track_types_temp():
    """Temporary track types API mit fake data"""
    try:
        # Fake data für jetzt
        fake_track_types = [
            {
                'id': 1,
                'name': 'Standard',
                'description': 'Standard gerade Bahn',
                'icon_url': '/static/track-icons/bahn_standard.png',
                'icon_filename': 'bahn_standard.png',
                'is_default': True,
                'is_placeholder': False
            },
            {
                'id': 2,
                'name': 'Kurve Links', 
                'description': 'Linkskurve',
                'icon_url': '/static/track-icons/bahn_kurve_links.png',
                'icon_filename': 'bahn_kurve_links.png',
                'is_default': False,
                'is_placeholder': False
            },
            {
                'id': 99,
                'name': 'Unbekannt',
                'description': 'Platzhalter für unbekannte Bahnen',
                'icon_url': '/static/track-icons/bahn_placeholder.png', 
                'icon_filename': 'bahn_placeholder.png',
                'is_default': False,
                'is_placeholder': True
            }
        ]
        
        return jsonify({
            'status': 'success',
            'track_types': fake_track_types
        })
        
    except Exception as e:
        logger.error(f"❌ Get track types error: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to load track types'}), 500

@app.route('/settings')
def settings_temp():
    """Temporary settings page"""
    try:
        # Für jetzt einfach die template rendern ohne echte Daten
        return render_template('settings.html')
        
    except Exception as e:
        logger.error(f"❌ Settings page error: {str(e)}")
        return f"<h1>Settings</h1><p>Settings page in development. Database models needed first.</p>", 200

# ------------------------------
# Error Handlers
# ------------------------------

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    logger.error(f"❌ Internal server error: {str(error)}")
    return render_template('500.html'), 500

# ------------------------------
# Application Startup & Initialization
# ------------------------------

def initialize_app():
    """Initialize the application on startup"""
    try:
        log_action("🚀 Gopher Minigolf App initializing")
        
        # Test database connection
        if check_database_connection():
            log_action("Database connection successful")
            
            # Check and create tables if needed
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

# Initialize app when module is imported (works with Gunicorn)
with app.app_context():
    initialize_app()

if __name__ == '__main__':
    # Configure for local development or manual run
    port = int(os.environ.get('PORT', 5001))
    debug = is_development()
    
    startup_msg = f"🏌️ Starting Gopher Minigolf App"
    if is_production():
        startup_msg += f" in PRODUCTION mode on port {port} 🛡️"
    else:
        startup_msg += f" in DEVELOPMENT mode on port {port} 🔧"
    
    logger.info(startup_msg)
    logger.info("📋 Auto-initialization is ENABLED - no manual /initdb needed!")
    
    app.run(host='0.0.0.0', port=port, debug=debug)