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

class Game(db.Model):
    __tablename__ = 'games'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    place = db.Column(db.String(100), nullable=False)
    track_count = db.Column(db.Integer, nullable=False, default=18)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    players = db.relationship('Player', backref='game', cascade="all, delete-orphan", lazy=True)
    
    def __repr__(self):
        return f'<Game {self.id}: {self.place} on {self.date}>'

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

def safe_database_init():
    """Safely initialize database tables"""
    try:
        if not check_database_connection():
            raise Exception("Database connection failed")
        
        # Create all tables (only creates missing ones)
        db.create_all()
        log_action("Database initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {str(e)}")
        return False

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        # Check database connection
        db_status = check_database_connection()
        
        # Get basic stats
        game_count = Game.query.count() if db_status else 0
        
        status = {
            'status': 'healthy' if db_status else 'unhealthy',
            'environment': get_environment(),
            'database': 'connected' if db_status else 'disconnected',
            'games_count': game_count,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(status), 200 if db_status else 503
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/initdb')
def initdb():
    """Initialize database - environment aware and safe"""
    try:
        if is_development():
            # Development: Allow optional reset
            reset_requested = request.args.get('reset', '').lower() == 'true'
            
            if reset_requested:
                log_action("Resetting database (development only)")
                db.drop_all()
                
            success = safe_database_init()
            
            if success:
                action = "reset and created" if reset_requested else "initialized"
                log_action(f"Database {action}")
                return f"✅ Development: Database {action} successfully."
            else:
                return "❌ Database initialization failed.", 500
                
        else:
            # Production: Only safe initialization
            success = safe_database_init()
            
            if success:
                log_action("Database safely initialized")
                return "✅ Production: Database safely initialized (no data lost)."
            else:
                return "❌ Database initialization failed.", 500
                
    except Exception as e:
        logger.error(f"❌ Database init error: {str(e)}")
        return f"<h1>Database Error</h1><p>{str(e)}</p>", 500

@app.route('/reset-dev-db')
def reset_dev_db():
    """Development only: Force reset database"""
    if not is_development():
        log_action("Unauthorized reset attempt blocked")
        return jsonify({'error': 'Only available in development environment'}), 403
    
    try:
        log_action("Performing complete database reset")
        db.drop_all()
        success = safe_database_init()
        
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
        
        if not db_connected:
            return jsonify({'error': 'Database not connected'}), 503
        
        # Gather statistics
        stats = {
            'environment': get_environment(),
            'database_type': 'PostgreSQL' if 'postgresql://' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite',
            'connection_status': 'connected',
            'tables': {
                'games': Game.query.count(),
                'players': Player.query.count(),
                'scores': Score.query.count()
            },
            'latest_game': None,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Get latest game info
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
    """Save new game with players and initial scores"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'status': 'error', 'message': 'No data received'}), 400
        
        # Validate required fields
        required_fields = ['date', 'place', 'players']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'status': 'error', 'message': f'Missing required field: {field}'}), 400
        
        # Create game
        game = Game(
            date=data.get('date'),
            place=data.get('place'),
            track_count=data.get('track_count', 18)
        )
        
        db.session.add(game)
        db.session.flush()  # Get game.id
        
        # Create players and scores
        players_data = data.get('players', [])
        track_count = game.track_count
        
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
        
        log_action(f"Game created: {game.place} ({len(players_data)} players, {track_count} tracks)")
        
        return jsonify({
            'status': 'success', 
            'game_id': game.id,
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
# Application Startup
# ------------------------------

def initialize_app():
    """Initialize the application on startup"""
    try:
        log_action("Application starting up")
        
        # Test database connection and initialize
        if check_database_connection():
            safe_database_init()
            log_action("Application ready")
        else:
            logger.error("❌ Failed to connect to database on startup")
            
    except Exception as e:
        logger.error(f"❌ Startup error: {str(e)}")

if __name__ == '__main__':
    with app.app_context():
        initialize_app()
    
    # Configure for Render.com
    port = int(os.environ.get('PORT', 5001))
    debug = is_development()
    
    startup_msg = f"Starting Gopher Minigolf App"
    if is_production():
        startup_msg += f" in PRODUCTION mode on port {port} 🛡️"
    else:
        startup_msg += f" in DEVELOPMENT mode on port {port} 🔧"
    
    logger.info(startup_msg)
    
    app.run(host='0.0.0.0', port=port, debug=debug)