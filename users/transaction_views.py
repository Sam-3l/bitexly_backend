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

from users.models import Transaction, Users
from users.serializers import (
    TransactionSerializer,
    TransactionListSerializer,
)

logger = logging.getLogger(__name__)


# ============================================================================
# PAGINATION CLASS
# ============================================================================
class TransactionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ============================================================================
# RECENT TRANSACTIONS VIEW
# ============================================================================
class RecentTransactionsView(APIView):
    """
    Get most recent transactions (last 10).
    Perfect for dashboard display.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get limit from query params
            limit = int(request.query_params.get('limit', 10))
            limit = min(limit, 50)  # Max 50
            
            # ✅ CRITICAL: Check if Transaction model exists and has data
            try:
                # Get user's recent transactions
                recent_txns = Transaction.objects.filter(
                    user=request.user
                ).order_by('-created_at')[:limit]
                
                # Convert to list to check count
                txn_list = list(recent_txns)
                
                logger.info(f"Found {len(txn_list)} recent transactions for user {request.user.email}")
                
                # ✅ Return empty array if no transactions (NOT error!)
                if len(txn_list) == 0:
                    return Response({
                        "success": True,
                        "count": 0,
                        "transactions": [],
                        "message": "No transactions found yet"
                    }, status=status.HTTP_200_OK)
                
                # Serialize the transactions
                serializer = TransactionListSerializer(txn_list, many=True)
                
                return Response({
                    "success": True,
                    "count": len(txn_list),
                    "transactions": serializer.data
                }, status=status.HTTP_200_OK)
                
            except Exception as db_error:
                # ✅ Specific database error handling
                logger.error(f"Database error in recent transactions: {str(db_error)}", exc_info=True)
                return Response({
                    "success": False,
                    "message": "Database error - Transaction table may not exist yet",
                    "details": str(db_error),
                    "hint": "Run migrations: python manage.py makemigrations && python manage.py migrate"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except ValueError as ve:
            # Invalid limit parameter
            logger.error(f"Invalid limit parameter: {str(ve)}")
            return Response({
                "success": False,
                "message": "Invalid limit parameter - must be a number"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            # General error
            logger.error(f"Recent transactions error: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Failed to fetch recent transactions",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# TRANSACTION HISTORY VIEW
# ============================================================================
class TransactionHistoryView(APIView):
    """
    Get user's transaction history with comprehensive filtering.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = TransactionPagination
    
    def get(self, request):
        try:
            # ✅ Check if table exists first
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
                
                # ✅ Check if empty
                count = queryset.count()
                logger.info(f"Found {count} transactions for user {request.user.email} with applied filters")
                
                if count == 0:
                    return Response({
                        "success": True,
                        "count": 0,
                        "results": [],
                        "message": "No transactions found matching your filters"
                    }, status=status.HTTP_200_OK)
                
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
                    "count": count,
                    "transactions": serializer.data
                }, status=status.HTTP_200_OK)
                
            except Exception as db_error:
                logger.error(f"Database error: {str(db_error)}", exc_info=True)
                return Response({
                    "success": False,
                    "message": "Database error - Transaction table may not exist",
                    "details": str(db_error),
                    "hint": "Run: python manage.py makemigrations && python manage.py migrate"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            logger.error(f"Transaction history error: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Failed to fetch transaction history",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# QUICK STATS VIEW
# ============================================================================
class QuickStatsView(APIView):
    """
    Get quick transaction statistics without heavy calculations.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            
            # ✅ Check if table exists
            try:
                user_txns = Transaction.objects.filter(user=user)
                
                # Quick aggregations
                total_transactions = user_txns.count()
                
                logger.info(f"User {user.email} has {total_transactions} total transactions")
                
                # If no transactions, return zeros (not error!)
                if total_transactions == 0:
                    return Response({
                        "success": True,
                        "stats": {
                            'total_transactions': 0,
                            'completed_transactions': 0,
                            'failed_transactions': 0,
                            'pending_transactions': 0,
                            'total_buys': 0,
                            'total_sells': 0,
                            'total_swaps': 0,
                            'total_fees_paid': "0.00000000",
                            'recent_transactions_count': 0,
                        },
                        "message": "No transactions yet"
                    }, status=status.HTTP_200_OK)
                
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
                
                return Response({
                    "success": True,
                    "stats": quick_stats
                }, status=status.HTTP_200_OK)
                
            except Exception as db_error:
                logger.error(f"Database error: {str(db_error)}", exc_info=True)
                return Response({
                    "success": False,
                    "message": "Database error - Transaction table may not exist",
                    "details": str(db_error),
                    "hint": "Run: python manage.py makemigrations && python manage.py migrate"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            logger.error(f"Quick stats error: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Failed to fetch quick stats",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# TRANSACTION DETAIL VIEW
# ============================================================================
class TransactionDetailView(APIView):
    """
    Get detailed information about a specific transaction.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, transaction_id):
        try:
            try:
                transaction = Transaction.objects.get(
                    transaction_id=transaction_id,
                    user=request.user
                )
                
                serializer = TransactionSerializer(transaction)
                
                return Response({
                    "success": True,
                    "transaction": serializer.data
                }, status=status.HTTP_200_OK)
            
            except Transaction.DoesNotExist:
                return Response({
                    "success": False,
                    "message": f"Transaction {transaction_id} not found or doesn't belong to you"
                }, status=status.HTTP_404_NOT_FOUND)
                
        except Exception as e:
            logger.error(f"Transaction detail error: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Internal server error",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# EXPORT TRANSACTIONS (CSV/JSON)
# ============================================================================
class ExportTransactionsView(APIView):
    """
    Export transactions as CSV or JSON.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            export_format = request.query_params.get('format', 'json').lower()
            
            # Get user transactions
            transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
            
            if transactions.count() == 0:
                return Response({
                    "success": False,
                    "message": "No transactions to export"
                }, status=status.HTTP_404_NOT_FOUND)
            
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
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Export error: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Export failed",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)