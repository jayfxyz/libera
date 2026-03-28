package api

import (
	"encoding/json"
	"log"
	"net/http"

	"github.com/gorilla/websocket"
	"github.com/web-libation/backend/internal/jobs"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		// TODO: restrict to APP_URL in production
		return true
	},
}

// WSHandler returns the download progress WebSocket handler for mounting outside /api.
func WSHandler(queue *jobs.Queue) http.HandlerFunc {
	h := &handlers{queue: queue}
	return h.downloadProgressWS
}

func (h *handlers) downloadProgressWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("ws upgrade: %v", err)
		return
	}
	defer conn.Close()

	ch := h.queue.Subscribe()
	defer h.queue.Unsubscribe(ch)

	// Read pump (consume pings / close messages)
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	}()

	for {
		select {
		case <-done:
			return
		case event, ok := <-ch:
			if !ok {
				return
			}
			b, _ := json.Marshal(event)
			if err := conn.WriteMessage(websocket.TextMessage, b); err != nil {
				return
			}
		}
	}
}
