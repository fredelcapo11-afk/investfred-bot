from flask import Flask, jsonify, render_template_string
import os
from datetime import datetime
import json

app = Flask(__name__)

# Intentar importar Supabase
try:
    from supabase_manager import SupabaseManager
    supabase = SupabaseManager()
    SUPABASE_AVAILABLE = True
except:
    supabase = None
    SUPABASE_AVAILABLE = False

@app.route('/')
def home():
    """Dashboard principal"""
    try:
        # Obtener datos si Supabase está disponible
        señales = []
        estadisticas = []
        logs = []
        
        if SUPABASE_AVAILABLE and supabase:
            import asyncio
            
            # Obtener señales recientes
            try:
                response = supabase.client.table('señales')\
                    .select('*')\\
                    .order('timestamp', desc=True)\\
                    .limit(10)\\
                    .execute()
                señales = response.data if response.data else []
            except:
                señales = []
            
            # Obtener estadísticas
            try:
                stats = asyncio.run(supabase.obtener_estadisticas_diarias(1))
                estadisticas = stats if stats else []
            except:
                estadisticas = []
            
            # Obtener logs
            try:
                response = supabase.client.table('logs_bot')\
                    .select('*')\\
                    .order('timestamp', desc=True)\\
                    .limit(20)\\
                    .execute()
                logs = response.data if response.data else []
            except:
                logs = []
        
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>🤖 InvestFred AI Dashboard</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="refresh" content="30">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                    color: #333;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.95);
                    border-radius: 20px;
                    padding: 30px;
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
                }
                .header {
                    text-align: center;
                    margin-bottom: 40px;
                    padding-bottom: 20px;
                    border-bottom: 3px solid #3498db;
                }
                .header h1 {
                    color: #2c3e50;
                    font-size: 2.5em;
                    margin-bottom: 10px;
                }
                .header p {
                    color: #7f8c8d;
                    font-size: 1.1em;
                }
                .status-badge {
                    display: inline-block;
                    padding: 8px 16px;
                    background: #27ae60;
                    color: white;
                    border-radius: 20px;
                    font-weight: bold;
                    margin-top: 10px;
                }
                .dashboard-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 25px;
                    margin-bottom: 40px;
                }
                .card {
                    background: white;
                    padding: 25px;
                    border-radius: 15px;
                    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.05);
                    border-left: 5px solid #3498db;
                    transition: transform 0.3s;
                }
                .card:hover {
                    transform: translateY(-5px);
                }
                .card h3 {
                    color: #2980b9;
                    margin-bottom: 20px;
                    font-size: 1.3em;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
                .card h3::before {
                    content: '';
                    width: 8px;
                    height: 8px;
                    background: #3498db;
                    border-radius: 50%;
                }
                .metric {
                    display: flex;
                    justify-content: space-between;
                    padding: 12px 0;
                    border-bottom: 1px solid #eee;
                }
                .metric:last-child {
                    border-bottom: none;
                }
                .metric-value {
                    font-weight: bold;
                    color: #2c3e50;
                }
                .table-container {
                    overflow-x: auto;
                    margin-top: 20px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    background: white;
                    border-radius: 10px;
                    overflow: hidden;
                }
                th {
                    background: #f8f9fa;
                    padding: 15px;
                    text-align: left;
                    color: #2c3e50;
                    font-weight: 600;
                    border-bottom: 2px solid #dee2e6;
                }
                td {
                    padding: 15px;
                    border-bottom: 1px solid #eee;
                }
                tr:last-child td {
                    border-bottom: none;
                }
                .badge {
                    display: inline-block;
                    padding: 5px 12px;
                    border-radius: 15px;
                    font-size: 0.85em;
                    font-weight: 600;
                }
                .badge-success {
                    background: #d4edda;
                    color: #155724;
                }
                .badge-warning {
                    background: #fff3cd;
                    color: #856404;
                }
                .badge-danger {
                    background: #f8d7da;
                    color: #721c24;
                }
                .badge-info {
                    background: #d1ecf1;
                    color: #0c5460;
                }
                .log-info { color: #3498db; }
                .log-warning { color: #f39c12; }
                .log-error { color: #e74c3c; }
                .footer {
                    text-align: center;
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    color: #7f8c8d;
                    font-size: 0.9em;
                }
                @media (max-width: 768px) {
                    .container {
                        padding: 15px;
                    }
                    .dashboard-grid {
                        grid-template-columns: 1fr;
                    }
                    th, td {
                        padding: 10px;
                    }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 InvestFred AI Dashboard</h1>
                    <p>Sistema de trading automatizado con inteligencia artificial</p>
                    <div class="status-badge">
                        {% if SUPABASE_AVAILABLE %}
                            ✅ SISTEMA OPERATIVO
                        {% else %}
                            ⚠️ MODO LOCAL
                        {% endif %}
                    </div>
                </div>
                
                <div class="dashboard-grid">
                    <div class="card">
                        <h3>📊 Estado del Sistema</h3>
                        <div class="metric">
                            <span>Supabase:</span>
                            <span class="metric-value">
                                {% if SUPABASE_AVAILABLE %}
                                    <span class="badge badge-success">CONECTADO</span>
                                {% else %}
                                    <span class="badge badge-warning">NO CONECTADO</span>
                                {% endif %}
                            </span>
                        </div>
                        <div class="metric">
                            <span>Última actualización:</span>
                            <span class="metric-value">{{ datetime.now().strftime('%H:%M:%S') }}</span>
                        </div>
                        <div class="metric">
                            <span>Señales activas:</span>
                            <span class="metric-value">{{ señales|selectattr('cerrada', 'equalto', false)|list|length }}</span>
                        </div>
                        <div class="metric">
                            <span>Base de datos:</span>
                            <span class="metric-value">
                                {% if estadisticas %}
                                    <span class="badge badge-success">ACTIVA</span>
                                {% else %}
                                    <span class="badge badge-info">SIN DATOS</span>
                                {% endif %}
                            </span>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>📈 Estadísticas Hoy</h3>
                        {% if estadisticas and estadisticas[0] %}
                        <div class="metric">
                            <span>Señales totales:</span>
                            <span class="metric-value">{{ estadisticas[0].señales_totales }}</span>
                        </div>
                        <div class="metric">
                            <span>Señales ganadoras:</span>
                            <span class="metric-value">{{ estadisticas[0].señales_ganadoras }}</span>
                        </div>
                        <div class="metric">
                            <span>Precisión:</span>
                            <span class="metric-value">{{ "%.1f"|format(estadisticas[0].precision) }}%</span>
                        </div>
                        {% else %}
                        <div class="metric">
                            <span>No hay datos disponibles</span>
                            <span class="metric-value">-</span>
                        </div>
                        {% endif %}
                    </div>
                </div>
                
                <div class="card">
                    <h3>📋 Últimas Señales</h3>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Ticker</th>
                                    <th>Precio</th>
                                    <th>Probabilidad</th>
                                    <th>Estado</th>
                                    <th>Hora</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for señal in señales[:10] %}
                                <tr>
                                    <td><strong>{{ señal.ticker }}</strong></td>
                                    <td>${{ "%.2f"|format(señal.precio) }}</td>
                                    <td>{{ "%.1f"|format(señal.probabilidad * 100) }}%</td>
                                    <td>
                                        {% if señal.cerrada %}
                                            {% if señal.resultado == 'Ganadora' %}
                                                <span class="badge badge-success">GANADORA</span>
                                            {% else %}
                                                <span class="badge badge-danger">PERDEDORA</span>
                                            {% endif %}
                                        {% else %}
                                            <span class="badge badge-warning">ACTIVA</span>
                                        {% endif %}
                                    </td>
                                    <td>{{ señal.timestamp[:16].replace('T', ' ') }}</td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="5" style="text-align: center; padding: 30px;">
                                        No hay señales registradas
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <div class="card">
                    <h3>📝 Logs del Sistema</h3>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Nivel</th>
                                    <th>Mensaje</th>
                                    <th>Origen</th>
                                    <th>Hora</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for log in logs[:15] %}
                                <tr>
                                    <td>
                                        <span class="log-{{ log.nivel|lower }} badge badge-{{ 'info' if log.nivel == 'INFO' else 'warning' if log.nivel == 'WARNING' else 'danger' }}">
                                            {{ log.nivel }}
                                        </span>
                                    </td>
                                    <td>{{ log.mensaje[:80] }}{% if log.mensaje|length > 80 %}...{% endif %}</td>
                                    <td>{{ log.origen }}</td>
                                    <td>{{ log.timestamp[:19].replace('T', ' ') }}</td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="4" style="text-align: center; padding: 30px;">
                                        No hay logs disponibles
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <div class="footer">
                    <p>InvestFred AI v2.0 | Sistema automatizado de trading</p>
                    <p>Última actualización: {{ datetime.now().strftime('%Y-%m-%d %H:%M:%S') }} | 
                    Actualiza automáticamente cada 30 segundos</p>
                    <p>
                        <a href="/health" style="color: #3498db; text-decoration: none;">Health Check</a> | 
                        <a href="/api/stats" style="color: #3498db; text-decoration: none;">API Stats</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        ''', 
        SUPABASE_AVAILABLE=SUPABASE_AVAILABLE,
        señales=señales,
        estadisticas=estadisticas,
        logs=logs,
        datetime=datetime)
        
    except Exception as e:
        return f"<h2>Error cargando dashboard:</h2><pre>{str(e)}</pre>"

@app.route('/health')
def health_check():
    """Endpoint para health check de Render"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "investfred-bot",
        "supabase": "connected" if SUPABASE_AVAILABLE else "disconnected",
        "version": "2.0.0"
    })

@app.route('/api/stats')
def api_stats():
    """API para estadísticas"""
    try:
        stats = {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "supabase_connected": SUPABASE_AVAILABLE
        }
        
        if SUPABASE_AVAILABLE and supabase:
            import asyncio
            try:
                # Obtener señales activas
                response = supabase.client.table('señales')\
                    .select('COUNT(*)')\\
                    .eq('cerrada', False)\\
                    .execute()
                stats['active_signals'] = response.data[0]['count'] if response.data else 0
                
                # Obtener estadísticas del día
                daily_stats = asyncio.run(supabase.obtener_estadisticas_diarias(1))
                stats['daily_stats'] = daily_stats if daily_stats else []
                
            except Exception as e:
                stats['error'] = str(e)
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/signals')
def api_signals():
    """API para señales recientes"""
    try:
        if SUPABASE_AVAILABLE and supabase:
            response = supabase.client.table('señales')\
                .select('*')\\
                .order('timestamp', desc=True)\\
                .limit(20)\\
                .execute()
            
            return jsonify({
                "count": len(response.data) if response.data else 0,
                "signals": response.data if response.data else []
            })
        else:
            return jsonify({"count": 0, "signals": [], "message": "Supabase no disponible"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
