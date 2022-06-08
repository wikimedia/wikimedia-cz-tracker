( function () {
	$.fn.dataTableExt.oSort[ 'money-pre' ] = function ( a ) {
		a = a.toString();
		if ( a === '' ) {
			return 0;
		}
		return parseFloat( a.replace( ',', '' ).replace( '.', '' ) );
	};
}() );
