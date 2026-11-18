
"""Annual single-store economics rebuilt from Case Appendix A2, A3, A5, A6, A7.

Case forecast values are not historical observations. Contribution margins for cafe
sales already include ordinary franchise charges. Do NOT double subtract royalties.
"""
from __future__ import annotations
from dataclasses import dataclass
from .inputs import Inputs, Overrides, OPTIONS, midpoint

@dataclass(frozen=True)
class UnitResult:
    typ: str
    option: str
    annual_sales_delta: float       # net new cafe food/drink sales incl. displaced purchases
    workspace_fees_gross: float
    workspace_fees_retained: float  # after operator share, before franchise charges
    annual_owner_contribution: float
    capex_owner: float
    annual_hq_royalty: float
    owner_npv_5y: float
    owner_simple_payback: float | None


def unit_economics(data: Inputs, typ: str, option: str, over: Overrides | None = None,
                   *, technology: str = 'licensed') -> UnitResult:
    """Single-store base case / sampled case with annual steady-state contribution.

    technology='licensed' means 3% fee + $1.8k per year at store for paid/membership.
    technology='custom' means those *store-level* SaaS fees are removed, with HQ
    fixed custom technology costs accounted for in financial_engine.py.
    """
    if option not in OPTIONS: raise ValueError(f'Unknown option {option!r}')
    if technology not in ('licensed','custom'): raise ValueError('technology must be licensed or custom')
    over=over or Overrides()
    d=lambda k: over.get(data,typ,k)
    g=lambda k: over.rule(data,k)
    sales_delta=fees=retained=contrib=capex=0.0
    if option in ('Paid Reservations','Operator Partnership'):
        peak_hours=d('reserved_seats')*g('peak_hours')*g('days')*midpoint(data,typ,'peak_sell_min','peak_sell_max',over)
        quiet_hours=d('reserved_seats')*(d('open_hours')-g('peak_hours'))*g('days')*midpoint(data,typ,'quiet_sell_min','quiet_sell_max',over)
        reservations=(peak_hours+quiet_hours)/d('reservation_length')
        lost_purchases=peak_hours*d('peak_use')/d('stay_hours')*midpoint(data,typ,'lost_walkin_min','lost_walkin_max',over)
        new_share = g('operator_new_visits') if option=='Operator Partnership' else d('new_reservation_share')
        sales_delta=(reservations*new_share-lost_purchases)*d('ticket')
        fees=(peak_hours+quiet_hours)*d('res_hour_price')
        if option=='Paid Reservations':
            retained=fees
            platform_share=d('saas_share') if technology=='licensed' else 0
            platform_fixed=d('saas_store_fixed') if technology=='licensed' else 0
            contrib=retained*(1-d('franchise_fee_workspace')-platform_share)+sales_delta*d('cafe_contrib')-d('res_opex')-platform_fixed
            capex=d('capex_res')
        else:
            retained=fees*(1-g('operator_keep'))
            contrib=retained*(1-d('franchise_fee_workspace'))+sales_delta*d('cafe_contrib')-d('partner_opex')
            capex=d('capex_partner')
    elif option=='Memberships':
        members=d('regulars')*d('consider_work')*midpoint(data,typ,'member_conv_min','member_conv_max',over)
        extra_hours=members*max(0,midpoint(data,typ,'member_hours_min','member_hours_max',over)-d('member_prior_hours'))*g('months')
        lost_purchases=extra_hours*d('member_peak_share')*d('peak_use')/d('stay_hours')*midpoint(data,typ,'lost_walkin_min','lost_walkin_max',over)
        sales_delta=(members*g('months')*d('extra_visits_member')-lost_purchases)*d('ticket')
        fees=retained=members*d('member_month_price')*g('months')
        platform_share=d('saas_share') if technology=='licensed' else 0
        platform_fixed=d('saas_store_fixed') if technology=='licensed' else 0
        contrib=retained*(1-d('franchise_fee_workspace')-platform_share)+sales_delta*d('cafe_contrib')-d('member_opex')-platform_fixed
        capex=d('capex_mem')
    elif option=='Late-day Offer':
        sales_delta=midpoint(data,typ,'late_tx_min','late_tx_max',over)*d('ticket')*g('days')
        contrib=sales_delta*(d('late_contrib')-d('late_waste'))-d('late_labour')
        capex=d('capex_late')
    elif option=='Corporate Accounts':
        accounts=midpoint(data,typ,'accounts_min','accounts_max',over)
        sales_delta=accounts*d('orders_per_week')*d('cups_per_order')*d('weeks_year')*d('cup_price')
        contrib=sales_delta*d('corp_contrib')
        capex=d('capex_corp')
    royalty=g('royalty')*(sales_delta+retained)
    rate=g('discount')
    pv_factor=sum((1+rate)**(-year) for year in range(1,6))
    npv=-capex+contrib*pv_factor
    payback=capex/contrib if contrib>0 else None
    return UnitResult(typ,option,sales_delta,fees,retained,contrib,capex,royalty,npv,payback)
