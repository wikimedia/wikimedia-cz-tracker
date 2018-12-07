( function () {
	function showHiddencomment() {
		$( this ).hide();
		$( this ).parent().find( '.hiddencomment' ).show();
		return false;
	}

	function processHiddencomment() {
		var switchDiv = $( this );
		switchDiv.find( '.hiddencomment' ).hide();
		switchDiv.find( 'a.unhide' ).click( showHiddencomment ).show();
	}

	$( document ).ready( function () {
		$( '.hide-switch' ).each( processHiddencomment );
	} );
}() );
