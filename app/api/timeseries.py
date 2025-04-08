# app/api/timeseries.py
from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from app.services.influxdb_client import InfluxDBClientService
from app.utils.dependencies import is_authenticated

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/timeseries", tags=["Time Series Data"])

# Instantiate InfluxDB client
influx_client = InfluxDBClientService()

@router.get("/query", dependencies=[Depends(is_authenticated)])
async def query_data(
    measurement: str = Query(..., description="Measurement name"),
    field: str = Query(..., description="Field to query"),
    source: Optional[str] = Query(None, description="Optional source filter (e.g., relay_id)"),
    start_time: datetime = Query(..., description="Start time (ISO format)"),
    end_time: datetime = Query(..., description="End time (ISO format)"),
    aggregation: str = Query("mean", description="Aggregation function (mean, max, min)"),
    interval: str = Query("1m", description="Aggregation interval (e.g., 1m, 5m, 1h)")
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
        
        # Format the timestamps properly for Flux queries (this is critical)
        # Must be in format: "YYYY-MM-DDThh:mm:ssZ" with quotes
        start_formatted = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_formatted = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Build the Flux query using a raw string to avoid escape issues
        flux_query = f'''from(bucket: "{influx_client.bucket}")
  |> range(start: {start_formatted}, stop: {end_formatted})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r._field == "{field}")'''
        
        # Add source filter if provided
        if source:
            flux_query += f'''
  |> filter(fn: (r) => r.relay_id == "{source}")'''
        
        # Add aggregation and yield
        flux_query += f'''
  |> aggregateWindow(every: {interval}, fn: {aggregation}, createEmpty: false)
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
        
        # Return structured response
        return {
            "measurement": measurement,
            "field": field,
            "source": source,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "interval": interval,
            "aggregation": aggregation,
            "data": records
        }
    except Exception as e:
        logger.error(f"Query failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
    finally:
        # Ensure client connection doesn't remain open
        try:
            await influx_client.close()
        except Exception as close_error:
            logger.error(f"Error closing InfluxDB connection: {close_error}")