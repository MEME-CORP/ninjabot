"""
Result reporting module for SPL Token Buy/Sell Script.
Handles formatting, exporting, and analyzing execution results.
"""

import json
import csv
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import time

from loguru import logger
from .wallet_swap_manager import ExecutionSummary, SwapResult
from .buy_sell_config import SwapConfiguration


class ResultReporter:
    """Generates comprehensive reports from execution results."""
    
    def __init__(self, output_dir: str = "data/reports"):
        """Initialize result reporter."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_console_report(self, summary: ExecutionSummary) -> str:
        """Generate a formatted console report."""
        config = summary.config
        
        # Header
        report_lines = [
            "=" * 80,
            f"SPL TOKEN {config.operation.value.upper()} EXECUTION REPORT",
            "=" * 80,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        # Configuration Summary
        report_lines.extend([
            "CONFIGURATION:",
            f"  Operation: {config.operation.value} {config.token_config.input_token} → {config.token_config.output_token}",
            f"  Amount Strategy: {config.amount_config.strategy.value}",
            f"  Execution Mode: {config.execution_config.mode.value}",
            f"  Slippage Tolerance: {config.execution_config.slippage_bps / 100:.2f}%",
            f"  Verification: {'Enabled' if config.execution_config.verify_swaps else 'Disabled'}",
            f"  Fee Collection: {'Enabled' if config.execution_config.collect_fees else 'Disabled'}",
            f"  Dry Run: {'Yes' if config.dry_run else 'No'}",
            ""
        ])
        
        # Execution Summary
        duration_str = f"{summary.duration:.2f}s" if summary.duration else "N/A"
        
        report_lines.extend([
            "EXECUTION SUMMARY:",
            f"  Status: {summary.execution_status.upper()}",
            f"  Duration: {duration_str}",
            f"  Total Wallets: {summary.total_wallets}",
            f"  Selected Wallets: {summary.selected_wallets}",
            f"  Successful Swaps: {summary.total_success_count}",
            f"  Failed Swaps: {summary.total_failure_count}",
            f"  Success Rate: {summary.overall_success_rate:.1f}%",
            ""
        ])
        
        # Volume Summary
        if summary.total_volume_in > 0:
            report_lines.extend([
                "VOLUME SUMMARY:",
                f"  Total Input Volume: {summary.total_volume_in:.6f} {config.token_config.input_token}",
                f"  Total Output Volume: {summary.total_volume_out:.6f} {config.token_config.output_token}",
                f"  Average Price Impact: {summary.average_price_impact:.2f}%" if summary.average_price_impact else "  Average Price Impact: N/A",
                f"  Total Fees Collected: {summary.total_fees_collected:.6f} SOL",
                ""
            ])
        
        # Batch Results
        if len(summary.batch_results) > 1:
            report_lines.extend([
                "BATCH RESULTS:",
                *[f"  {batch.batch_id}: {batch.success_count}/{len(batch.swap_results)} successful ({batch.success_rate:.1f}%) - {batch.duration:.2f}s" 
                  for batch in summary.batch_results],
                ""
            ])
        
        # Error Analysis
        if summary.total_failure_count > 0:
            error_counts = self._analyze_errors(summary.all_swap_results)
            report_lines.extend([
                "ERROR ANALYSIS:",
                *[f"  {error_type}: {count} failures" for error_type, count in error_counts.items()],
                ""
            ])
        
        # Individual Results Summary (if not too many)
        if len(summary.all_swap_results) <= 20:
            report_lines.extend([
                "INDIVIDUAL RESULTS:",
                "  Idx | Wallet Address           | Status    | Input    | Output   | TX ID",
                "  " + "-" * 75,
            ])
            
            for result in summary.all_swap_results:
                status = "SUCCESS" if result.is_successful else "FAILED"
                input_amt = f"{result.actual_input_amount:.4f}" if result.actual_input_amount else "N/A"
                output_amt = f"{result.actual_output_amount:.4f}" if result.actual_output_amount else "N/A"
                tx_id = (result.final_transaction_id[:12] + "...") if result.final_transaction_id else "N/A"
                
                report_lines.append(
                    f"  {result.wallet_index:3d} | {result.wallet_address[:24]} | {status:9s} | {input_amt:8s} | {output_amt:8s} | {tx_id}"
                )
            
            report_lines.append("")
        
        # Footer
        report_lines.extend([
            "=" * 80,
            f"Report generated by SPL Token Buy/Sell Script at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80
        ])
        
        return "\n".join(report_lines)
    
    def save_detailed_report(self, summary: ExecutionSummary, format: str = "json") -> str:
        """Save detailed report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        operation = summary.config.operation.value
        filename = f"{operation}_report_{timestamp}.{format}"
        filepath = self.output_dir / filename
        
        if format.lower() == "json":
            report_data = self._create_json_report(summary)
            with open(filepath, 'w') as f:
                json.dump(report_data, f, indent=2, default=str)
        
        elif format.lower() == "csv":
            self._create_csv_report(summary, filepath)
        
        elif format.lower() == "yaml":
            report_data = self._create_yaml_report(summary)
            with open(filepath, 'w') as f:
                yaml.dump(report_data, f, default_flow_style=False)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        logger.info(f"Detailed report saved: {filepath}")
        return str(filepath)
    
    def _create_json_report(self, summary: ExecutionSummary) -> Dict[str, Any]:
        """Create comprehensive JSON report."""
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "report_version": "1.0",
                "script_version": "1.0.0"
            },
            "configuration": {
                "operation": summary.config.operation.value,
                "tokens": {
                    "input": summary.config.token_config.input_token,
                    "output": summary.config.token_config.output_token,
                    "input_mint": summary.config.token_config.input_mint,
                    "output_mint": summary.config.token_config.output_mint
                },
                "amount_strategy": {
                    "strategy": summary.config.amount_config.strategy.value,
                    "base_amount": summary.config.amount_config.base_amount,
                    "percentage": summary.config.amount_config.percentage,
                    "min_amount": summary.config.amount_config.min_amount,
                    "max_amount": summary.config.amount_config.max_amount
                },
                "execution": {
                    "mode": summary.config.execution_config.mode.value,
                    "max_concurrent": summary.config.execution_config.max_concurrent,
                    "slippage_bps": summary.config.execution_config.slippage_bps,
                    "verify_swaps": summary.config.execution_config.verify_swaps,
                    "collect_fees": summary.config.execution_config.collect_fees,
                    "retry_failed": summary.config.execution_config.retry_failed,
                    "max_retries": summary.config.execution_config.max_retries
                },
                "dry_run": summary.config.dry_run
            },
            "execution_summary": {
                "status": summary.execution_status,
                "start_time": summary.start_time,
                "end_time": summary.end_time,
                "duration_seconds": summary.duration,
                "total_wallets": summary.total_wallets,
                "selected_wallets": summary.selected_wallets,
                "successful_swaps": summary.total_success_count,
                "failed_swaps": summary.total_failure_count,
                "success_rate_percent": summary.overall_success_rate,
                "error_message": summary.error_message
            },
            "volume_summary": {
                "total_input_volume": summary.total_volume_in,
                "total_output_volume": summary.total_volume_out,
                "average_price_impact_percent": summary.average_price_impact,
                "total_fees_collected": summary.total_fees_collected,
                "input_token": summary.config.token_config.input_token,
                "output_token": summary.config.token_config.output_token
            },
            "batch_results": [
                {
                    "batch_id": batch.batch_id,
                    "start_time": batch.start_time,
                    "end_time": batch.end_time,
                    "duration_seconds": batch.duration,
                    "total_swaps": len(batch.swap_results),
                    "successful_swaps": batch.success_count,
                    "failed_swaps": batch.failure_count,
                    "success_rate_percent": batch.success_rate
                }
                for batch in summary.batch_results
            ],
            "amount_calculations": [
                {
                    "wallet_index": result.wallet_index,
                    "wallet_address": result.wallet_address,
                    "calculated_amount": result.calculated_amount,
                    "strategy_used": result.strategy_used.value,
                    "source_balance": result.source_balance,
                    "percentage_used": result.percentage_used,
                    "is_valid": result.is_valid,
                    "error": result.error
                }
                for result in summary.amount_calculation_results
            ],
            "swap_results": [
                {
                    "wallet_index": result.wallet_index,
                    "wallet_address": result.wallet_address,
                    "input_token": result.input_token,
                    "output_token": result.output_token,
                    "input_amount": result.input_amount,
                    "status": result.status.value,
                    "is_successful": result.is_successful,
                    "final_transaction_id": result.final_transaction_id,
                    "actual_input_amount": result.actual_input_amount,
                    "actual_output_amount": result.actual_output_amount,
                    "price_impact": result.price_impact,
                    "fee_collected": result.fee_collected,
                    "start_time": result.start_time,
                    "end_time": result.end_time,
                    "total_duration": result.total_duration,
                    "attempt_count": result.attempt_count,
                    "final_error": result.final_error,
                    "error_classification": result.error_classification,
                    "attempts": [
                        {
                            "attempt_number": attempt.attempt_number,
                            "start_time": attempt.start_time,
                            "end_time": attempt.end_time,
                            "duration": attempt.duration,
                            "status": attempt.status.value,
                            "error": attempt.error,
                            "transaction_id": attempt.transaction_id
                        }
                        for attempt in result.attempts
                    ]
                }
                for result in summary.all_swap_results
            ],
            "error_analysis": self._analyze_errors(summary.all_swap_results)
        }
    
    def _create_csv_report(self, summary: ExecutionSummary, filepath: Path) -> None:
        """Create CSV report with swap results."""
        with open(filepath, 'w', newline='') as csvfile:
            fieldnames = [
                'wallet_index', 'wallet_address', 'input_token', 'output_token',
                'input_amount', 'status', 'transaction_id', 'actual_input_amount',
                'actual_output_amount', 'price_impact', 'fee_collected',
                'duration', 'attempt_count', 'error_classification', 'final_error'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in summary.all_swap_results:
                writer.writerow({
                    'wallet_index': result.wallet_index,
                    'wallet_address': result.wallet_address,
                    'input_token': result.input_token,
                    'output_token': result.output_token,
                    'input_amount': result.input_amount,
                    'status': result.status.value,
                    'transaction_id': result.final_transaction_id or '',
                    'actual_input_amount': result.actual_input_amount or '',
                    'actual_output_amount': result.actual_output_amount or '',
                    'price_impact': result.price_impact or '',
                    'fee_collected': result.fee_collected or '',
                    'duration': result.total_duration or '',
                    'attempt_count': result.attempt_count,
                    'error_classification': result.error_classification or '',
                    'final_error': result.final_error or ''
                })
    
    def _create_yaml_report(self, summary: ExecutionSummary) -> Dict[str, Any]:
        """Create YAML-friendly report structure."""
        # Similar to JSON but with simplified structure for readability
        return {
            "execution_info": {
                "operation": summary.config.operation.value,
                "tokens": f"{summary.config.token_config.input_token} → {summary.config.token_config.output_token}",
                "status": summary.execution_status,
                "duration": f"{summary.duration:.2f}s" if summary.duration else "N/A",
                "success_rate": f"{summary.overall_success_rate:.1f}%"
            },
            "results": {
                "total_wallets": summary.total_wallets,
                "successful": summary.total_success_count,
                "failed": summary.total_failure_count,
                "total_volume_in": summary.total_volume_in,
                "total_volume_out": summary.total_volume_out,
                "fees_collected": summary.total_fees_collected
            },
            "individual_swaps": [
                {
                    "wallet": f"#{result.wallet_index} ({result.wallet_address[:12]}...)",
                    "status": result.status.value,
                    "amount": f"{result.input_amount} → {result.actual_output_amount or 'N/A'}",
                    "tx_id": result.final_transaction_id or "N/A",
                    "error": result.final_error or None
                }
                for result in summary.all_swap_results
            ]
        }
    
    def _analyze_errors(self, swap_results: List[SwapResult]) -> Dict[str, int]:
        """Analyze and count error types."""
        error_counts = {}
        
        for result in swap_results:
            if not result.is_successful and result.error_classification:
                error_type = result.error_classification
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        return error_counts
    
    def generate_summary_stats(self, summary: ExecutionSummary) -> Dict[str, Any]:
        """Generate summary statistics for analysis."""
        successful_results = [r for r in summary.all_swap_results if r.is_successful]
        
        if not successful_results:
            return {
                "total_swaps": len(summary.all_swap_results),
                "successful_swaps": 0,
                "success_rate": 0.0,
                "error": "No successful swaps to analyze"
            }
        
        # Calculate statistics
        input_amounts = [r.actual_input_amount for r in successful_results if r.actual_input_amount]
        output_amounts = [r.actual_output_amount for r in successful_results if r.actual_output_amount]
        price_impacts = [r.price_impact for r in successful_results if r.price_impact is not None]
        durations = [r.total_duration for r in successful_results if r.total_duration is not None]
        
        stats = {
            "total_swaps": len(summary.all_swap_results),
            "successful_swaps": len(successful_results),
            "success_rate": summary.overall_success_rate,
            "volume_stats": {
                "total_input": sum(input_amounts),
                "total_output": sum(output_amounts),
                "average_input": sum(input_amounts) / len(input_amounts) if input_amounts else 0,
                "average_output": sum(output_amounts) / len(output_amounts) if output_amounts else 0,
                "min_input": min(input_amounts) if input_amounts else 0,
                "max_input": max(input_amounts) if input_amounts else 0
            },
            "performance_stats": {
                "average_duration": sum(durations) / len(durations) if durations else 0,
                "min_duration": min(durations) if durations else 0,
                "max_duration": max(durations) if durations else 0,
                "average_price_impact": sum(price_impacts) / len(price_impacts) if price_impacts else 0,
                "max_price_impact": max(price_impacts) if price_impacts else 0
            },
            "error_analysis": self._analyze_errors(summary.all_swap_results),
            "fees_collected": summary.total_fees_collected
        }
        
        return stats
    
    def create_html_report(self, summary: ExecutionSummary) -> str:
        """Create HTML report for web viewing."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        operation = summary.config.operation.value
        filename = f"{operation}_report_{timestamp}.html"
        filepath = self.output_dir / filename
        
        # Generate HTML content
        html_content = self._generate_html_content(summary)
        
        with open(filepath, 'w') as f:
            f.write(html_content)
        
        logger.info(f"HTML report saved: {filepath}")
        return str(filepath)
    
    def _generate_html_content(self, summary: ExecutionSummary) -> str:
        """Generate HTML content for the report."""
        stats = self.generate_summary_stats(summary)
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>SPL Token {summary.config.operation.value.title()} Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f0f8ff; padding: 20px; border-radius: 5px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat-box {{ background: #f9f9f9; padding: 15px; border-radius: 5px; flex: 1; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #333; }}
        .stat-label {{ color: #666; font-size: 12px; }}
        .success {{ color: #28a745; }}
        .failed {{ color: #dc3545; }}
        .warning {{ color: #ffc107; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .status-success {{ background-color: #d4edda; }}
        .status-failed {{ background-color: #f8d7da; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>SPL Token {summary.config.operation.value.title()} Execution Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Operation: {summary.config.token_config.input_token} → {summary.config.token_config.output_token}</p>
    </div>
    
    <div class="summary">
        <div class="stat-box">
            <div class="stat-value success">{summary.total_success_count}</div>
            <div class="stat-label">Successful Swaps</div>
        </div>
        <div class="stat-box">
            <div class="stat-value failed">{summary.total_failure_count}</div>
            <div class="stat-label">Failed Swaps</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{summary.overall_success_rate:.1f}%</div>
            <div class="stat-label">Success Rate</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{summary.total_volume_in:.4f}</div>
            <div class="stat-label">Total Input Volume</div>
        </div>
    </div>
    
    <h2>Individual Swap Results</h2>
    <table>
        <tr>
            <th>Wallet #</th>
            <th>Address</th>
            <th>Status</th>
            <th>Input Amount</th>
            <th>Output Amount</th>
            <th>Price Impact</th>
            <th>Duration</th>
            <th>Transaction ID</th>
        </tr>
"""
        
        for result in summary.all_swap_results:
            status_class = "status-success" if result.is_successful else "status-failed"
            tx_link = f'<a href="https://solscan.io/tx/{result.final_transaction_id}" target="_blank">{result.final_transaction_id[:12]}...</a>' if result.final_transaction_id else "N/A"
            
            html += f"""
        <tr class="{status_class}">
            <td>{result.wallet_index}</td>
            <td>{result.wallet_address[:12]}...</td>
            <td>{result.status.value}</td>
            <td>{result.actual_input_amount:.6f if result.actual_input_amount else 'N/A'}</td>
            <td>{result.actual_output_amount:.6f if result.actual_output_amount else 'N/A'}</td>
            <td>{result.price_impact:.2f}% if result.price_impact else 'N/A'</td>
            <td>{result.total_duration:.2f}s if result.total_duration else 'N/A'</td>
            <td>{tx_link}</td>
        </tr>
"""
        
        html += """
    </table>
    
    <h2>Configuration Details</h2>
    <table>
        <tr><td>Amount Strategy</td><td>{}</td></tr>
        <tr><td>Execution Mode</td><td>{}</td></tr>
        <tr><td>Slippage Tolerance</td><td>{:.2f}%</td></tr>
        <tr><td>Verification</td><td>{}</td></tr>
        <tr><td>Fee Collection</td><td>{}</td></tr>
    </table>
    
</body>
</html>""".format(
            summary.config.amount_config.strategy.value,
            summary.config.execution_config.mode.value,
            summary.config.execution_config.slippage_bps / 100,
            "Enabled" if summary.config.execution_config.verify_swaps else "Disabled",
            "Enabled" if summary.config.execution_config.collect_fees else "Disabled"
        )
        
        return html


def create_quick_report(summary: ExecutionSummary) -> str:
    """Create a quick summary report for console output."""
    reporter = ResultReporter()
    return reporter.generate_console_report(summary)


def save_execution_results(summary: ExecutionSummary, format: str = "json", output_dir: str = "data/reports") -> str:
    """Save execution results to file."""
    reporter = ResultReporter(output_dir)
    return reporter.save_detailed_report(summary, format) 