# app/api/timeseries.py
from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional
from datetime import datetime, timedelta
import logging
from app.services.influxdb_client import InfluxDBReader
from app.utils.dependencies import is_authenticated

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/timeseries", tags=["Time Series Data"], dependencies=[Depends(is_authenticated)])

# Instantiate InfluxDB client
influx_client = InfluxDBReader()

@router.get("/query", )
async def query_data(
    measurement: str = Query(..., description="Measurement name"),
    field: str = Query(..., description="Field to query"),
    source: Optional[str] = Query(None, description="Optional source filter (e.g., relay_id)"),
    start_time: datetime = Query(..., description="Start time (ISO format)"),
    end_time: datetime = Query(..., description="End time (ISO format)"),
    aggregation: str = Query("mean", description="Aggregation function (mean, max, min)"),
    interval: str = Query("1m", description="Aggregation interval (e.g., 1m, 5m, 1h)"),
    limit: Optional[int] = Query(None, description="Optional limit on number of data points")
):
    """
    Query time series data with aggregation.
    
    This endpoint provides data for the Historical Chart.
    """
    try:
        # Validate aggregation method
        valid_aggs = ["mean", "max", "min", "sum", "count", "first", "last"]
        if aggregation not in valid_aggs:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid aggregation function. Valid options: {', '.join(valid_aggs)}"
            )
        
        # Format the timestamps properly for Flux queries
        start_formatted = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_formatted = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Calculate time difference for optimization
        time_diff = end_time - start_time
        
        # Check if the time range is very large and interval is very small
        # This is a simple way to prevent extremely heavy queries
        if time_diff > timedelta(days=14) and interval in ["10s", "30s"]:
            # Log a warning about this heavy query
            logger.warning(f"Very heavy query detected: {time_diff.days} days with {interval} interval")
            
            # For large time ranges with small intervals, we might need to limit points
            if limit is None and time_diff > timedelta(days=30) and interval in ["10s", "30s", "1m", "2m", "5m"]:
                # Calculate a reasonable downsampling factor
                days = time_diff.days
                # Very conservative limit - adjust as needed based on system performance
                limit = min(100000, 10000 * (1 + days // 10))
                logger.info(f"Automatically limiting results to {limit} points")
        
        # Build the Flux query using a raw string to avoid escape issues
        flux_query = f'''from(bucket: "{influx_client.bucket}")
  |> range(start: {start_formatted}, stop: {end_formatted})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r._field == "{field}")'''
        
        # Add source filter if provided
        if source:
            flux_query += f'''
  |> filter(fn: (r) => r.relay_id == "{source}")'''
        
        # Add aggregation
        flux_query += f'''
  |> aggregateWindow(every: {interval}, fn: {aggregation}, createEmpty: false)'''
        
        # Add limit if specified
        if limit:
            # When using limit, it's best to ensure data is chronological
            flux_query += f'''
  |> sort(columns: ["_time"], desc: false)
  |> limit(n: {limit})'''
            
        # Finally add yield
        flux_query += f'''
  |> yield(name: "{aggregation}")'''
        
        # Log the query for debugging
        logger.debug(f"Executing Flux query: {flux_query}")
        
        # Execute the query using proper connection handling
        tables = await influx_client.query(flux_query)
        
        # Transform the result into a list of records
        records = []
        for table in tables:
            for record in table.records:
                records.append({
                    "time": record.get_time().isoformat(),
                    "value": record.get_value()
                })
        
        # Return structured response with point count
        return {
            "measurement": measurement,
            "field": field,
            "source": source,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "interval": interval,
            "aggregation": aggregation,
            "point_count": len(records),
            "data": records
        }
    except Exception as e:
        logger.error(f"Query failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.get("/auto-interval")
async def calculate_auto_interval(
    start_time: datetime = Query(..., description="Start time (ISO format)"),
    end_time: datetime = Query(..., description="End time (ISO format)"),
    max_points: int = Query(2000, description="Target maximum number of data points")
):
    """
    Calculate the optimal interval for the given time range to achieve the target number of points.
    
    This helps clients automatically determine the best granularity for their queries.
    """
    try:
        # Calculate time difference in seconds
        time_diff = (end_time - start_time).total_seconds()
        
        # Calculate the ideal interval in seconds
        ideal_interval_seconds = max(1, time_diff / max_points)
        
        # Map to standard intervals
        available_intervals = [
            {"seconds": 10, "interval": "10s"},
            {"seconds": 30, "interval": "30s"},
            {"seconds": 60, "interval": "1m"},
            {"seconds": 120, "interval": "2m"},
            {"seconds": 300, "interval": "5m"},
            {"seconds": 600, "interval": "10m"},
            {"seconds": 900, "interval": "15m"},
            {"seconds": 1800, "interval": "30m"},
            {"seconds": 3600, "interval": "1h"},
            {"seconds": 10800, "interval": "3h"},
            {"seconds": 21600, "interval": "6h"},
            {"seconds": 43200, "interval": "12h"},
            {"seconds": 86400, "interval": "1d"}
        ]
        
        # Find the closest interval that doesn't exceed max_points
        chosen_interval = available_intervals[-1]["interval"]  # Default to the largest interval
        
        for interval in available_intervals:
            if interval["seconds"] >= ideal_interval_seconds:
                chosen_interval = interval["interval"]
                break
        
        # Calculate the estimated number of points this interval will generate
        estimated_points = int(time_diff / next(i["seconds"] for i in available_intervals if i["interval"] == chosen_interval))
        
        return {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "time_diff_seconds": time_diff,
            "target_max_points": max_points,
            "ideal_interval_seconds": ideal_interval_seconds,
            "recommended_interval": chosen_interval,
            "estimated_points": estimated_points
        }
    except Exception as e:
        logger.error(f"Auto interval calculation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Calculation failed: {str(e)}")


@router.get("/available-intervals")
async def get_available_intervals():
    """
    Return a list of available time intervals for aggregation.
    
    This helps clients understand what intervals are supported.
    """
    intervals = [
        {"value": "10s", "label": "10 seconds", "category": "High Resolution"},
        {"value": "30s", "label": "30 seconds", "category": "High Resolution"},
        {"value": "1m", "label": "1 minute", "category": "High Resolution"},
        {"value": "2m", "label": "2 minutes", "category": "Medium Resolution"},
        {"value": "5m", "label": "5 minutes", "category": "Medium Resolution"},
        {"value": "10m", "label": "10 minutes", "category": "Medium Resolution"},
        {"value": "15m", "label": "15 minutes", "category": "Low Resolution"},
        {"value": "30m", "label": "30 minutes", "category": "Low Resolution"},
        {"value": "1h", "label": "1 hour", "category": "Low Resolution"},
        {"value": "3h", "label": "3 hours", "category": "Low Resolution"},
        {"value": "6h", "label": "6 hours", "category": "Low Resolution"},
        {"value": "12h", "label": "12 hours", "category": "Low Resolution"},
        {"value": "1d", "label": "1 day", "category": "Low Resolution"}
    ]
    
    return {
        "intervals": intervals
    }