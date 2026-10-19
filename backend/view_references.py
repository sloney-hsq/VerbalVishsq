"""Presentation ordinals shared by model projections and dashboard inspection.

Matches the frontend: ordinary cards (including quantitative bins), then category
matrices, retaining source order within each group. Never rewrites committed IDs.
"""


def chart_display_numbers(views):
    def matrix(view):
        return view.get('chart_type') == 'heatmap' and view.get('result_kind') != 'binned_2d'

    ordered = [v for v in views if not matrix(v)] + [v for v in views if matrix(v)]
    return {view['id']: index for index, view in enumerate(ordered, 1) if 'id' in view}
