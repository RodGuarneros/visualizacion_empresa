
# A/B test bebidas · datos sintéticos 2023–2026

Este paquete contiene un modelo relacional pensado para PostgreSQL/pgAdmin y para ser consultado desde Python + Streamlit usando SQLAlchemy.

## Horizonte temporal
- Desde: 2023-01-01
- Hasta: 2026-12-31

## Tablas
- dim_regions
- dim_channels
- dim_products
- dim_customers
- dim_experiments
- fact_sessions
- fact_orders

## Lógica del experimento
Experimento principal:
- Variante A = control
- Variante B = recomendación personalizada + promo más visible

La variante B tiene una mejora sintética moderada en:
- click-through rate
- add to cart
- purchase rate

## Tamaño generado
- Regiones: 8
- Canales: 5
- Productos: 10
- Clientes: 24,000
- Sesiones: 180,000
- Órdenes: 1,360

## Métricas disponibles
- sessions
- impressions
- clicks
- add_to_cart
- purchases
- orders
- ctr
- purchase_rate
- net_revenue_mxn
- margin_mxn
- revenue_per_session_mxn

## Vista útil para Streamlit
- ab_beverages.vw_ab_test_summary

## Recomendación de carga
1. Crear el esquema con `ab_beverages_schema.sql`
2. Cargar los CSV en el mismo orden de dimensiones a hechos
3. Conectarse desde Streamlit usando SQLAlchemy

## Notas
Los datos son sintéticos, pero modelados para parecer plausibles en un contexto de bebidas:
- marcas premium y core
- canales digitales y tradicionales
- estacionalidad ligera
- mejor desempeño de la variante B en digital
