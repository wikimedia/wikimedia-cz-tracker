( function () {
	function dateWithNoneToOrder( date ) {
		var datePattern = /\d{4}-\d{2}-\d{2}/;
		if ( datePattern.test( date ) ) {
			return parseInt( String( date ).replace( '-', '' ) );
		}
		return 0;
	}

	$.fn.dataTableExt.oSort[ 'date-with-none-asc' ] = function ( a, b ) {
		var ordA = dateWithNoneToOrder( a ),
			ordB = dateWithNoneToOrder( b );
		return ordA - ordB;
	};
	$.fn.dataTableExt.oSort[ 'date-with-none-desc' ] = function ( a, b ) {
		var ordA = dateWithNoneToOrder( a ),
			ordB = dateWithNoneToOrder( b );
		return ordB - ordA;
	};
	$.fn.dataTableExt.oSort[ 'money-pre' ] = function ( a ) {
		a = a.toString();
		if ( a === '' ) {
			return 0;
		}
		return parseFloat( a.replace( ',', '' ).replace( '.', '' ) );
	};
}() );
