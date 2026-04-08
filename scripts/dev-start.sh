#!/bin/bash
# NeoChatPlatform Development Helper Script
# Usage: ./scripts/dev-start.sh [command]
#
# Commands:
#   start         - Start backend services (docker) + frontend (optional)
#   frontend      - Start frontend dev server only
#   stop          - Stop all services
#   restart       - Restart all services
#   rebuild       - Rebuild images and restart all services
#   logs          - Show logs for all services
#   status        - Show service status
#   migrate       - Run database migrations
#   shell         - Open shell in running API container
#   test          - Run tests (requires test infra running)
#   setup         - First time setup (create .env, pull images)
#   teardown      - Stop services and remove volumes

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="-f docker-compose.dev.yml"
COMPOSE="docker-compose $COMPOSE_FILE -p neo-chat-platform-dev"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if command exists
check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is required but not installed."
        exit 1
    fi
}

# Ensure we're in the project directory
cd "$PROJECT_DIR"

# Parse command
COMMAND="${1:-start}"

case "$COMMAND" in
    setup)
        log_info "First time setup..."

        # Check dependencies
        check_cmd docker
        check_cmd docker-compose
        check_cmd tmux

        # Create .env from example if it doesn't exist
        if [ ! -f .env ]; then
            cp .env.example .env
            log_success "Created .env from .env.example"
            log_warn "Please edit .env and fill in your credentials!"
        else
            log_info ".env already exists"
        fi

        # Pull latest images
        log_info "Pulling latest images..."
        docker-compose $COMPOSE_FILE pull

        log_success "Setup complete! Run './scripts/dev-start.sh start' to begin."
        ;;

    start)
        log_info "Starting NeoChatPlatform backend services..."

        # Check if tmux is running
        if command -v tmux &> /dev/null && [ -n "$TMUX" ]; then
            log_warn "You're already inside a tmux session. Starting services without tmux panes..."
            $COMPOSE up -d
        elif command -v tmux &> /dev/null; then
            # Check if session already exists
            if tmux has-session -t neochat-dev 2>/dev/null; then
                log_warn "tmux session 'neochat-dev' already exists. Attaching..."
                tmux attach -t neochat-dev
                exit 0
            fi

            log_info "Starting services in tmux with multi-pane view..."

            # Kill existing session if any
            tmux kill-session -t neochat-dev 2>/dev/null || true

            # Create new tmux session
            tmux new-session -d -s neochat-dev -n "api"

            # Start all services in detached mode
            $COMPOSE up -d

            # Split window and start logs for each service
            tmux split-window -h -t neochat-dev
            tmux split-window -v -t neochat-dev:0.1
            tmux split-window -v -t neochat-dev:0.2
            tmux split-window -v -t neochat-dev:0.3

            # Send logs commands to each pane
            tmux send-keys -t neochat-dev:0.0 "echo '=== API LOGS ===' && $COMPOSE logs -f api" Enter
            tmux send-keys -t neochat-dev:0.1 "echo '=== CONVERSATION WORKER LOGS ===' && $COMPOSE logs -f conversation-worker" Enter
            tmux send-keys -t neochat-dev:0.2 "echo '=== OUTBOUND WORKER LOGS ===' && $COMPOSE logs -f outbound-worker" Enter
            tmux send-keys -t neochat-dev:0.3 "echo '=== RABBITMQ LOGS ===' && $COMPOSE logs -f rabbitmq" Enter

            # Set layout
            tmux select-layout -t neochat-dev tiled

            log_success "Services started in tmux session 'neochat-dev'"
            log_info "Run 'tmux attach -t neochat-dev' to view logs"
            log_info "Press Ctrl+B then D to detach"
        else
            log_warn "tmux not found. Starting services without multi-pane logs..."
            $COMPOSE up -d
        fi

        # Wait for services to be healthy
        log_info "Waiting for services to be healthy..."
        sleep 5

        # Show status
        $COMPOSE ps

        # Auto-run migrations if needed
        if [ "$2" == "--with-migrate" ] || [ "$2" == "-m" ]; then
            log_info "Running database migrations..."
            ./scripts/dev-start.sh migrate
        fi

        log_success "Backend services started!"
        log_info "To start the frontend: ./scripts/dev-start.sh frontend"
        ;;

    frontend)
        if [ ! -d "frontend" ]; then
            log_error "frontend directory not found. Are you in the project root?"
            exit 1
        fi
        if [ ! -f "frontend/package.json" ]; then
            log_error "frontend/package.json not found. Run 'cd frontend && npm install' first."
            exit 1
        fi
        log_info "Starting frontend dev server at http://localhost:3000..."
        log_info "API backend must be running separately (./scripts/dev-start.sh start)"
        cd frontend && npm run dev
        ;;

    stop)
        log_info "Stopping NeoChatPlatform services..."
        $COMPOSE down
        log_success "Services stopped."
        ;;

    restart)
        log_info "Restarting NeoChatPlatform services..."
        $COMPOSE restart
        log_success "Services restarted."
        ;;

    rebuild)
        log_info "Rebuilding and restarting all services..."
        $COMPOSE down
        $COMPOSE up -d --build
        log_success "Rebuild complete."
        $COMPOSE ps
        ;;

    status)
        log_info "Service status:"
        $COMPOSE ps
        ;;

    logs)
        if command -v tmux &> /dev/null && tmux has-session -t neochat-dev 2>/dev/null; then
            log_info "Attaching to existing tmux session..."
            tmux attach -t neochat-dev
        else
            SERVICE="${2:-}"
            if [ -n "$SERVICE" ]; then
                $COMPOSE logs -f "$SERVICE"
            else
                $COMPOSE logs -f
            fi
        fi
        ;;

    migrate)
        log_info "Running database migrations..."
        $COMPOSE exec api alembic upgrade head
        log_success "Migrations complete."
        ;;

    rollback)
        log_info "Rolling back last migration..."
        $COMPOSE exec api alembic downgrade -1
        log_success "Rollback complete."
        ;;

    current)
        log_info "Current migration:"
        $COMPOSE exec api alembic current
        ;;

    history)
        log_info "Migration history:"
        $COMPOSE exec api alembic history
        ;;

    shell)
        log_info "Opening shell in API container..."
        $COMPOSE exec api /bin/sh
        ;;

    psql)
        log_info "Opening PostgreSQL shell..."
        $COMPOSE exec postgres psql -U neochat -d neochat
        ;;

    rabbitmq)
        log_info "Opening RabbitMQ management UI..."
        echo "URL: http://localhost:15672"
        echo "User: guest"
        echo "Pass: guest"
        ;;

    test)
        check_cmd uv
        log_info "Running tests..."
        DATABASE_URL="postgresql+asyncpg://neochat:changeme@localhost:5432/neochat" \
            uv run pytest tests/ -v --tb=short
        ;;

    test-unit)
        check_cmd uv
        log_info "Running unit tests..."
        uv run pytest tests/unit/ -v --tb=short
        ;;

    test-integration)
        check_cmd uv
        log_info "Running integration tests..."
        # Ensure test infra is running
        if ! docker ps --format '{{.Names}}' | grep -q neo-chat-platform-test; then
            log_warn "Test infrastructure not running. Starting..."
            docker-compose -f docker-compose.test.yml up -d
            sleep 5
        fi
        DATABASE_URL="postgresql+asyncpg://neochat:changeme@localhost:5432/neochat" \
            uv run pytest tests/integration/ -v --tb=short
        ;;

    test-infra-start)
        log_info "Starting test infrastructure..."
        docker-compose -f docker-compose.test.yml up -d
        sleep 5
        docker-compose -f docker-compose.test.yml ps
        log_success "Test infrastructure started."
        ;;

    test-infra-stop)
        log_info "Stopping test infrastructure..."
        docker-compose -f docker-compose.test.yml down -v
        log_success "Test infrastructure stopped."
        ;;

    teardown)
        log_warn "Stopping services and removing volumes..."
        $COMPOSE down -v
        log_success "Teardown complete."
        ;;

    *)
        echo "NeoChatPlatform Development Helper"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  setup                - First time setup (create .env, pull images)"
        echo "  start                - Start backend services (docker) + show tmux logs"
        echo "  frontend             - Start frontend dev server (Next.js, port 3000)"
        echo "  stop                 - Stop all backend services"
        echo "  restart              - Restart all backend services"
        echo "  rebuild              - Rebuild images and restart services"
        echo "  status               - Show service status"
        echo "  logs [service]      - Show logs (all or specific service)"
        echo "  migrate              - Run database migrations"
        echo "  rollback             - Rollback last migration"
        echo "  current              - Show current migration"
        echo "  history              - Show migration history"
        echo "  shell                - Open shell in API container"
        echo "  psql                 - Open PostgreSQL shell"
        echo "  rabbitmq             - Show RabbitMQ management URL"
        echo "  test                 - Run all tests"
        echo "  test-unit            - Run unit tests only"
        echo "  test-integration     - Run integration tests only"
        echo "  test-infra-start     - Start test infrastructure"
        echo "  test-infra-stop      - Stop test infrastructure"
        echo "  teardown             - Stop services and remove volumes"
        echo ""
        echo "Examples:"
        echo "  $0 setup                   # First time setup"
        echo "  $0 start                   # Start backend services"
        echo "  $0 start --with-migrate    # Start with migrations"
        echo "  $0 frontend                # Start frontend dev server (Next.js)"
        echo "  $0 logs api                # Show only API logs"
        echo "  $0 migrate                 # Run migrations"
        echo "  $0 test                    # Run all tests"
        echo "  $0 teardown                # Clean everything"
        ;;
esac
