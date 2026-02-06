from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging

from .models import Transaction, TransactionStats, Users
from .serializers import (
    TransactionSerializer,
    TransactionListSerializer,
    TransactionStatsSerializer,
    QuickStatsSerializer
)
from .permisssion import IsTrader

logger = logging.getLogger(__name__)


# ============================================================================
# PAGINATION CLASS
# ============================================================================
class TransactionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ============================================================================
# TRANSACTION HISTORY VIEW (Enhanced with Filters)
# ============================================================================
class TransactionHistoryView(APIView):
    """
    Get user's transaction history with comprehensive filtering.
    
    Query Parameters:
    - provider: Filter by provider (MELD, ONRAMP, MOONPAY, FINCHPAY, CHANGELLY)
    - type: Filter by type (BUY, SELL, SWAP)
    - status: Filter by status (PENDING, COMPLETED, FAILED, etc.)
    - source_currency: Filter by source currency (e.g., USD, BTC)
    - destination_currency: Filter by destination currency (e.g., USDT, EUR)
    - date_from: Filter from date (ISO format: 2024-01-01)
    - date_to: Filter to date (ISO format: 2024-12-31)
    - search: Search in transaction IDs, currencies
    - page: Page number
    - page_size: Results per page (max 100)
    - ordering: Order by field (e.g., -created_at, status)
    """
    permission_classes = [IsAuthenticated, IsTrader]
    pagination_class = TransactionPagination
    
    def get(self, request):
        try:
            # Base queryset - only user's transactions
            queryset = Transaction.objects.filter(user=request.user)
            
            # ============== FILTERS ==============
            
            # Filter by provider
            provider = request.query_params.get('provider')
            if provider:
                queryset = queryset.filter(provider=provider.upper())
            
            # Filter by transaction type
            txn_type = request.query_params.get('type')
            if txn_type:
                queryset = queryset.filter(transaction_type=txn_type.upper())
            
            # Filter by status
            txn_status = request.query_params.get('status')
            if txn_status:
                queryset = queryset.filter(status=txn_status.upper())
            
            # Filter by source currency
            source_currency = request.query_params.get('source_currency')
            if source_currency:
                queryset = queryset.filter(source_currency__iexact=source_currency)
            
            # Filter by destination currency
            destination_currency = request.query_params.get('destination_currency')
            if destination_currency:
                queryset = queryset.filter(destination_currency__iexact=destination_currency)
            
            # Filter by date range
            date_from = request.query_params.get('date_from')
            if date_from:
                queryset = queryset.filter(created_at__gte=date_from)
            
            date_to = request.query_params.get('date_to')
            if date_to:
                queryset = queryset.filter(created_at__lte=date_to)
            
            # Search in transaction IDs and currencies
            search = request.query_params.get('search')
            if search:
                queryset = queryset.filter(
                    Q(transaction_id__icontains=search) |
                    Q(provider_transaction_id__icontains=search) |
                    Q(source_currency__icontains=search) |
                    Q(destination_currency__icontains=search)
                )
            
            # ============== ORDERING ==============
            ordering = request.query_params.get('ordering', '-created_at')
            queryset = queryset.order_by(ordering)
            
            # ============== PAGINATION ==============
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(queryset, request)
            
            if page is not None:
                serializer = TransactionListSerializer(page, many=True)
                return paginator.get_paginated_response(serializer.data)
            
            # If no pagination
            serializer = TransactionListSerializer(queryset, many=True)
            return Response({
                "success": True,
                "count": queryset.count(),
                "transactions": serializer.data
            })
        
        except Exception as e:
            logger.error(f"Transaction history error: {str(e)}", exc_info=True)
            return Response(
                {"success": False, "message": "Failed to fetch transaction history", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# TRANSACTION DETAIL VIEW
# ============================================================================
class TransactionDetailView(APIView):
    """
    Get detailed information about a specific transaction.
    """
    permission_classes = [IsAuthenticated, IsTrader]
    
    def get(self, request, transaction_id):
        try:
            transaction = Transaction.objects.get(
                transaction_id=transaction_id,
                user=request.user
            )
            
            serializer = TransactionSerializer(transaction)
            
            return Response({
                "success": True,
                "transaction": serializer.data
            })
        
        except Transaction.DoesNotExist:
            return Response(
                {"success": False, "message": "Transaction not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Transaction detail error: {str(e)}", exc_info=True)
            return Response(
                {"success": False, "message": "Internal server error", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# TRANSACTION STATISTICS VIEW
# ============================================================================
class TransactionStatisticsView(APIView):
    """
    Get comprehensive transaction statistics for the user.
    Includes:
    - Total transactions (all, completed, failed, pending)
    - Breakdown by type (buy, sell, swap)
    - Breakdown by provider
    - Total fees paid
    - Recent activity
    """
    permission_classes = [IsAuthenticated, IsTrader]
    
    def get(self, request):
        try:
            user = request.user
            
            # Get or create stats object
            stats, created = TransactionStats.objects.get_or_create(user=user)
            
            # Update stats
            stats.update_stats()
            
            # Get additional breakdowns
            user_txns = Transaction.objects.filter(user=user)
            
            # Provider breakdown
            provider_breakdown = user_txns.values('provider').annotate(
                count=Count('id'),
                completed=Count('id', filter=Q(status='COMPLETED'))
            ).order_by('-count')
            
            # Monthly breakdown (last 6 months)
            six_months_ago = timezone.now() - timedelta(days=180)
            monthly_data = user_txns.filter(
                created_at__gte=six_months_ago
            ).extra(
                select={'month': "DATE_TRUNC('month', created_at)"}
            ).values('month').annotate(
                count=Count('id'),
                completed=Count('id', filter=Q(status='COMPLETED'))
            ).order_by('month')
            
            # Recent transactions (last 7 days)
            seven_days_ago = timezone.now() - timedelta(days=7)
            recent_count = user_txns.filter(created_at__gte=seven_days_ago).count()
            
            # Response data
            stats_data = TransactionStatsSerializer(stats).data
            stats_data['provider_breakdown'] = list(provider_breakdown)
            stats_data['monthly_data'] = list(monthly_data)
            stats_data['recent_transactions_count'] = recent_count
            
            return Response({
                "success": True,
                "statistics": stats_data
            })
        
        except Exception as e:
            logger.error(f"Statistics error: {str(e)}", exc_info=True)
            return Response(
                {"success": False, "message": "Failed to fetch statistics", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# QUICK STATS VIEW (Lightweight)
# ============================================================================
class QuickStatsView(APIView):
    """
    Get quick transaction statistics without heavy calculations.
    Use this for dashboard widgets.
    """
    permission_classes = [IsAuthenticated, IsTrader]
    
    def get(self, request):
        try:
            user = request.user
            user_txns = Transaction.objects.filter(user=user)
            
            # Quick aggregations
            total_transactions = user_txns.count()
            completed_transactions = user_txns.filter(status='COMPLETED').count()
            failed_transactions = user_txns.filter(status='FAILED').count()
            pending_transactions = user_txns.filter(status__in=['PENDING', 'PROCESSING']).count()
            
            total_buys = user_txns.filter(transaction_type='BUY').count()
            total_sells = user_txns.filter(transaction_type='SELL').count()
            total_swaps = user_txns.filter(transaction_type='SWAP').count()
            
            # Total fees
            fees_sum = user_txns.filter(status='COMPLETED').aggregate(
                total=Sum('total_fees')
            )['total'] or Decimal('0.00000000')
            
            # Recent transactions (last 7 days)
            seven_days_ago = timezone.now() - timedelta(days=7)
            recent_count = user_txns.filter(created_at__gte=seven_days_ago).count()
            
            quick_stats = {
                'total_transactions': total_transactions,
                'completed_transactions': completed_transactions,
                'failed_transactions': failed_transactions,
                'pending_transactions': pending_transactions,
                'total_buys': total_buys,
                'total_sells': total_sells,
                'total_swaps': total_swaps,
                'total_fees_paid': str(fees_sum),
                'recent_transactions_count': recent_count,
            }
            
            serializer = QuickStatsSerializer(quick_stats)
            
            return Response({
                "success": True,
                "stats": serializer.data
            })
        
        except Exception as e:
            logger.error(f"Quick stats error: {str(e)}", exc_info=True)
            return Response(
                {"success": False, "message": "Failed to fetch quick stats", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# RECENT TRANSACTIONS VIEW (for Dashboard)
# ============================================================================
class RecentTransactionsView(APIView):
    """
    Get most recent transactions (last 10).
    Perfect for dashboard display.
    """
    permission_classes = [IsAuthenticated, IsTrader]
    
    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 10))
            limit = min(limit, 50)  # Max 50
            
            recent_txns = Transaction.objects.filter(
                user=request.user
            ).order_by('-created_at')[:limit]
            
            serializer = TransactionListSerializer(recent_txns, many=True)
            
            return Response({
                "success": True,
                "count": recent_txns.count(),
                "transactions": serializer.data
            })
        
        except Exception as e:
            logger.error(f"Recent transactions error: {str(e)}", exc_info=True)
            return Response(
                {"success": False, "message": "Failed to fetch recent transactions", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# EXPORT TRANSACTIONS (CSV/JSON)
# ============================================================================
class ExportTransactionsView(APIView):
    """
    Export transactions as CSV or JSON.
    Query param: format=csv or format=json (default: json)
    """
    permission_classes = [IsAuthenticated, IsTrader]
    
    def get(self, request):
        try:
            export_format = request.query_params.get('format', 'json').lower()
            
            # Get user transactions
            transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
            
            if export_format == 'csv':
                import csv
                from django.http import HttpResponse
                
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="transactions_{timezone.now().strftime("%Y%m%d")}.csv"'
                
                writer = csv.writer(response)
                writer.writerow([
                    'Transaction ID', 'Date', 'Provider', 'Type', 'Status',
                    'Source Currency', 'Source Amount', 'Destination Currency', 
                    'Destination Amount', 'Exchange Rate', 'Total Fees', 'Network'
                ])
                
                for txn in transactions:
                    writer.writerow([
                        txn.transaction_id,
                        txn.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        txn.provider,
                        txn.transaction_type,
                        txn.status,
                        txn.source_currency,
                        str(txn.source_amount),
                        txn.destination_currency,
                        str(txn.destination_amount) if txn.destination_amount else '',
                        str(txn.exchange_rate) if txn.exchange_rate else '',
                        str(txn.total_fees),
                        txn.network or ''
                    ])
                
                return response
            
            else:  # JSON
                serializer = TransactionSerializer(transactions, many=True)
                return Response({
                    "success": True,
                    "count": transactions.count(),
                    "transactions": serializer.data,
                    "exported_at": timezone.now().isoformat()
                })
        
        except Exception as e:
            logger.error(f"Export error: {str(e)}", exc_info=True)
            return Response(
                {"success": False, "message": "Export failed", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )