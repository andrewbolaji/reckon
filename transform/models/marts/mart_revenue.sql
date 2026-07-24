/*
  Revenue Mart
  Daily revenue aggregation from Stripe payments,
  broken down by service category and payment method.
*/

with payments as (
    select * from {{ ref('stg_stripe_payments') }}
),

daily_revenue as (
    select
        date_trunc('day', payment_timestamp)::date as payment_date,
        service_description,
        payment_method,
        count(*)                                   as transaction_count,
        sum(amount_dollars)                        as revenue_dollars,
        round(avg(amount_dollars), 2)              as avg_ticket_dollars,
        count(case when status = 'refunded' then 1 end) as refund_count,
        coalesce(sum(case when status = 'refunded' then amount_dollars end), 0) as refund_dollars
    from payments
    group by 1, 2, 3
)

select
    payment_date,
    service_description,
    payment_method,
    transaction_count,
    revenue_dollars,
    avg_ticket_dollars,
    refund_count,
    refund_dollars,
    revenue_dollars - refund_dollars as net_revenue_dollars
from daily_revenue
order by payment_date, service_description
